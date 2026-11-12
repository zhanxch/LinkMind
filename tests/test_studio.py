"""Studio ownership, durable user requirements and non-replayed robot calls."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.request import Request, urlopen
from urllib.error import HTTPError

from roborag.episode_files import write_json
from roborag.studio.service import Studio, ROOT, serve


class StudioTests(unittest.TestCase):
    def setUp(self):
        auth = patch('roborag.studio.codex_agent.login_status', return_value={"available":False,"logged_in":False,"label":"test"})
        auth.start()
        self.addCleanup(auth.stop)
        self.tmp = tempfile.TemporaryDirectory()
        self.studio = Studio(state=self.tmp.name)
        self.task = self.studio.create_task(dict(task="push_T", goal="Align the block", constraints="Use small motions", profile="none"))

    def tearDown(self):
        self.studio.close()
        self.tmp.cleanup()

    def seed_run(self, run_id="run1", status="ready"):
        directory = self.studio.state / "runs" / run_id
        directory.mkdir()
        write_json(directory / "studio-run.json", dict(id=run_id, task_id=self.task["id"], task="push_T", status=status,
                    profile="none", created_at="2026-01-01", task_snapshot=self.task, control_fault=None))
        return directory

    def test_requirements_and_correction_survive_restart_without_becoming_success(self):
        self.seed_run(status="failed")
        self.studio.correction(self.task["id"], dict(text="Check orientation first", run_id="run1"))
        self.studio.close()
        self.studio = Studio(state=self.tmp.name)
        context = self.studio.context("run1")
        self.assertEqual(context["task"]["constraints"], "Use small motions")
        self.assertEqual(context["task"]["corrections"][0]["validation"], "unverified")
        self.assertEqual(context["run"]["status"], "failed")

    def test_correction_cannot_reference_another_task(self):
        self.seed_run(status="failed")
        other = self.studio.create_task(dict(task="stack_bowls", goal="Stack"))
        with self.assertRaisesRegex(ValueError, "different task"):
            self.studio.correction(other["id"], dict(text="No", run_id="run1"))

    def test_profile_and_scene_validation(self):
        for data in [dict(task="stack_bowls", goal="Stack", profile="none"), dict(task="push_T", goal="x", layout=-1),
                     dict(task="push_T", goal=""), dict(task="push_T", goal="x", seed=True)]:
            with self.assertRaises(ValueError):
                self.studio.create_task(data)

    def test_service_lease_prevents_two_owners(self):
        with self.assertRaises(BlockingIOError):
            Studio(state=self.tmp.name)

    def test_task_assignment_cannot_switch_conversations(self):
        self.seed_run(status="failed")
        with self.assertRaisesRegex(ValueError, "does not own"):
            self.studio.check_session("chat-a", task_id=self.task["id"])
        self.studio.bind_session(self.task["id"], "chat-a")
        self.assertTrue(self.studio.check_session("chat-a", run_id="run1")["allowed"])
        with self.assertRaisesRegex(ValueError, "different conversation"):
            self.studio.bind_session(self.task["id"], "chat-b")
        with self.assertRaisesRegex(ValueError, "does not own"):
            self.studio.check_session("chat-b", run_id="run1")

    def test_old_run_cannot_control_new_episode(self):
        self.seed_run(status="stopped")
        with self.assertRaisesRegex(ValueError, "not ready"):
            self.studio.call("run1", dict(call_id="a", tool="execute_chunk", arguments={}))

    def test_identical_call_returns_receipt_once_including_image(self):
        self.seed_run()
        result = {"content": [{"type":"image", "mimeType":"image/png", "data":"original-image-bytes"}]}
        with patch.object(self.studio, "require_active", return_value=self.studio.run("run1")), \
             patch.object(self.studio, "tools", return_value={"tools":[{"name":"observe"}]}), \
             patch.object(self.studio, "native_request", return_value=result) as send:
            data = dict(call_id="a", tool="observe", arguments={})
            self.assertEqual(self.studio.call("run1", data), result)
            self.assertEqual(self.studio.call("run1", data), result)
            self.assertEqual(send.call_count, 1)
            with self.assertRaisesRegex(ValueError, "different arguments"):
                self.studio.call("run1", {**data, "arguments":{"calibration":True}})

    def test_unknown_outcome_blocks_replay_and_new_motion(self):
        self.seed_run()
        with patch.object(self.studio, "require_active", side_effect=lambda _:self.studio.run("run1")), \
             patch.object(self.studio, "tools", return_value={"tools":[{"name":"execute_chunk"}]}), \
             patch.object(self.studio, "native_request", side_effect=TimeoutError) as send:
            data = dict(call_id="move1", tool="execute_chunk", arguments={})
            with self.assertRaisesRegex(RuntimeError, "unknown"):
                self.studio.call("run1", data)
            with self.assertRaisesRegex(ValueError, "unknown outcome"):
                self.studio.call("run1", data)
            with self.assertRaisesRegex(ValueError, "motion is blocked"):
                self.studio.call("run1", {**data, "call_id":"move2"})
            self.assertEqual(send.call_count, 1)

    def test_profile_does_not_expose_a_removed_tool(self):
        self.seed_run()
        with patch.object(self.studio, "require_active", return_value=self.studio.run("run1")), \
             patch.object(self.studio, "tools", return_value={"tools":[{"name":"observe"}]}), \
             patch.object(self.studio, "native_request") as send:
            with self.assertRaisesRegex(ValueError, "not available"):
                self.studio.call("run1", dict(call_id="a", tool="retrieve_evidence", arguments={}))
            send.assert_not_called()

    def test_native_tool_error_does_not_authorize_more_motion(self):
        self.seed_run()
        with patch.object(self.studio, "require_active", side_effect=lambda _:self.studio.run("run1")), \
             patch.object(self.studio, "tools", return_value={"tools":[{"name":"execute_chunk"}]}), \
             patch.object(self.studio, "native_request", return_value={"isError":True,"content":[]}) as send:
            self.studio.call("run1", dict(call_id="a", tool="execute_chunk", arguments={}))
            with self.assertRaisesRegex(ValueError, "motion is blocked"):
                self.studio.call("run1", dict(call_id="b", tool="execute_chunk", arguments={}))
            self.assertEqual(send.call_count, 1)

    def test_stop_waits_for_actual_process_exit(self):
        directory = self.seed_run()
        proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"], start_new_session=True)
        self.studio.active, self.studio.process = "run1", proc
        self.studio.log = (directory / "runner.log").open("w")
        stopped = self.studio.stop("run1")
        self.assertIsNotNone(proc.poll())
        self.assertEqual(stopped["status"], "stopped")
        self.assertIsNone(stopped["result"])
        self.assertIsNone(self.studio.active)

    def test_only_allowlisted_artifacts_are_served(self):
        self.seed_run(status="failed")
        for name in ("../../local.runtime.json", "studio-agent.json", "unknown"):
            with self.assertRaises(ValueError): self.studio.asset("run1", name)

    def test_all_published_banks_expose_source_linked_experience(self):
        for task in self.studio.manifest:
            entries = self.studio.experience(task)
            self.assertTrue(entries, task)
            self.assertTrue(all(len(e["source"]["sha256"])==64 for e in entries))

    def test_selected_experience_is_exact_and_preserves_uncertainty(self):
        entries = self.studio.experience("push_T", "push_T-0000")
        self.assertEqual([e["id"] for e in entries], ["push_T-0000"])
        self.assertIn("无法完全确认", entries[0]["summary"])
        with self.assertRaisesRegex(ValueError, "does not exist"):
            self.studio.experience("stack_bowls", "push_T-0000")

    def test_http_requires_token_and_rejects_non_object_body(self):
        server=serve(self.studio, 0, "test-token")
        thread=threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        url=f"http://127.0.0.1:{server.server_port}"
        try:
            with self.assertRaises(HTTPError) as error: urlopen(url+"/api/state")
            self.assertEqual(error.exception.code, 401)
            req=Request(url+"/api/tasks", b'[]', {"Authorization":"Bearer test-token"})
            with self.assertRaises(HTTPError) as error: urlopen(req)
            self.assertEqual(error.exception.code, 400)
        finally:
            server.shutdown(); server.server_close(); thread.join()


if __name__ == "__main__":
    unittest.main()
