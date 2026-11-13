import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from roborag.studio.camera import LiveCamera


class CameraTests(unittest.TestCase):
    def test_attachment_forwards_once_and_never_publishes_rejected_steps(self):
        with tempfile.TemporaryDirectory() as directory:
            native=Mock(return_value='native-result')
            api=SimpleNamespace(_env=SimpleNamespace(take_action=native),_cached_obs='old')
            camera=LiveCamera(directory)
            camera.publish=Mock()
            camera.attach(api)
            command={'joints':[1,2,3]}
            self.assertEqual(api._env.take_action(command),'native-result')
            native.assert_called_once_with(command)
            camera.publish.assert_called_once_with(api)
            self.assertIsNone(api._cached_obs)
            native.side_effect=ValueError('Native rejected action')
            with self.assertRaisesRegex(ValueError,'Native rejected action'):
                api._env.take_action(command)
            camera.publish.assert_called_once()

    def test_throttled_public_rgb_does_not_dispatch_actions(self):
        with tempfile.TemporaryDirectory() as directory:
            clock=Mock(return_value=0)
            api=SimpleNamespace(step=3, observe=Mock(return_value={'png':{'head':b'frame1','wrist_l':b'left'}}))
            camera=LiveCamera(directory, fps=4, clock=clock, wall_clock=lambda:100)
            camera.publish(api)
            camera.publish(api)
            api.observe.assert_called_once()
            self.assertEqual(json.loads((Path(directory)/'frame.json').read_text())['step'],3)
            clock.return_value=.25
            api.step=4
            api.observe.return_value={'png':{'head':b'frame2','wrist_l':b'left'}}
            camera.publish(api)
            self.assertEqual((Path(directory)/'head.png').read_bytes(),b'frame2')
            self.assertEqual(json.loads((Path(directory)/'frame.json').read_text())['frame'],2)
            self.assertFalse(list(Path(directory).glob('*.tmp')))

    def test_display_failure_keeps_last_frame_and_recovers(self):
        with tempfile.TemporaryDirectory() as directory:
            api=SimpleNamespace(step=0, observe=Mock(return_value={'png':{'head':b'original'}}))
            camera=LiveCamera(directory)
            camera.publish(api,force=True)
            api.observe.side_effect=RuntimeError('Camera offline')
            camera.publish(api,force=True)
            self.assertEqual((Path(directory)/'head.png').read_bytes(),b'original')
            self.assertTrue((Path(directory)/'error.json').exists())
            # Even failure to write the diagnostic must not turn control into a failure/retry.
            with patch('roborag.studio.camera.write_json',side_effect=OSError('Disk full')):
                camera.publish(api,force=True)
            api.observe.side_effect=None
            camera.publish(api,force=True)
            self.assertFalse((Path(directory)/'error.json').exists())

    def test_empty_cameras_do_not_publish_a_successful_frame(self):
        with tempfile.TemporaryDirectory() as directory:
            camera=LiveCamera(directory)
            camera.publish(SimpleNamespace(step=0,observe=lambda:{'png':{}}))
            self.assertFalse((Path(directory)/'frame.json').exists())
            self.assertTrue((Path(directory)/'error.json').exists())


if __name__ == '__main__':
    unittest.main()
