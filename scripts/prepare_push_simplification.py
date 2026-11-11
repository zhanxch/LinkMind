#!/usr/bin/env python3
"""Freeze two TRAIN references independently of any evaluation trajectory."""
import asyncio
import hashlib
import json
import tempfile
from pathlib import Path

from roborag.episode_files import write_json
from roborag.mcp.session import EpisodeMemory
from roborag.mcp.server import create_server
from roborag.rag_tasks import prompt_for
from roborag.push_simplification import (ROOT, PROFILES, FIXED_SOURCES, FIXED_PACKAGE,
                                       evidence_callbacks, prompt_for_profile)


async def main():
    bank = ROOT / "artifacts/generalization-v3-full/push_T"
    with tempfile.TemporaryDirectory() as temp:
        memory = EpisodeMemory(bank, ROOT / "data", temp, temp, "push_T", controller="delta")
        callback = evidence_callbacks(memory, None)["read_action_reference"]
        package = dict(schema="push-t-fixed-train-reference-v1", sources=FIXED_SOURCES,
                       selection="One preparation phase per arm, section=close; fixed before native tests. "
                                 "No evaluation images, states or trajectories are included.", references={}, source_sha256={})
        for arm, source in FIXED_SOURCES.items():
            memory.references.add(source)
            result = callback(source, include_actions=False, images=True, section="close")
            package["references"][arm] = result.model_dump(mode="json", exclude_none=True)
            graph = memory.bank.graph(source.split(":")[0])
            original = memory.bank.source(graph)
            package["source_sha256"][str(original)] = hashlib.sha256(original.read_bytes()).hexdigest()
            assert package["source_sha256"][str(original)] == graph["source"]["sha256"]
        if FIXED_PACKAGE.exists():
            assert json.loads(FIXED_PACKAGE.read_text()) == package, "Refuse to replace a different fixed package"
        else:
            write_json(FIXED_PACKAGE, package)
        profiles = {}
        for profile in PROFILES:
            memory.push_simplification = profile
            # Fixed/none explicitly discard the bank; restore only for building another surface.
            if memory.bank is None:
                memory = EpisodeMemory(bank, ROOT / "data", temp, temp, "push_T", controller="delta")
                memory.push_simplification = profile
            text = prompt_for_profile(prompt_for(ROOT, "push_T", "delta"), profile)
            tools = await create_server(memory).list_tools()
            profiles[profile] = dict(prompt_characters=len(text), prompt_sha256=hashlib.sha256(text.encode()).hexdigest(),
                                     tools=[t.model_dump(mode="json", exclude_none=True) for t in tools])
    write_json(ROOT / "results/push-simplification-surfaces.json", dict(
        profiles=profiles, fixed_package=str(FIXED_PACKAGE),
        fixed_package_sha256=hashlib.sha256(FIXED_PACKAGE.read_bytes()).hexdigest(),
        source_sha256=package["source_sha256"]))
    print(json.dumps({k:dict(prompt_characters=v['prompt_characters'],tools=[t['name'] for t in v['tools']])
                      for k,v in profiles.items()},ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())
