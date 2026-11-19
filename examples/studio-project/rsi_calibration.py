"""A two-round scalar-control calibration demo. No model, simulator or GPU required."""
import json
import os
from pathlib import Path
from statistics import mean

targets = [-2, 0, 2, 4]
bias = 0
out = Path(os.environ['LINKMIND_RUN_OUTPUT'])
out.mkdir(parents=True,exist_ok=True)
# The test plant adds a constant offset to each requested position.
with (out/'rounds.jsonl').open('x') as sink:
    for i in range(2):
        residuals = [target - (target + bias + 1) for target in targets]
        row = dict(version=1,series='Calibration demo '+out.parent.name[:8],protocol='fixed targets v1, simulated offset +1',
                   id='r'+str(i),parent='r0' if i else '',agent_version='bias='+str(bias),
                   change='Correct mean tracking error' if i else 'Initial controller',
                   status='evaluated',metrics={'mean_absolute_error':mean(map(abs,residuals))})
        sink.write(json.dumps(row)+'\n')
        sink.flush()
        bias += mean(residuals)
