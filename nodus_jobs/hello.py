"""
Step 2 of the Nodus plan: prove login + credits work.
    nodus run nodus_jobs/hello.py        -> should print 49
(No GPU on purpose: SAGE doesn't need one and GPUs burn credits fast.)
"""
import nodus

app = nodus.App("hello")


@app.function(timeout="5m", max_cost=0.5)
def square(x):
    return x * x


@app.local_entrypoint()
def main():
    print(square.remote(7))   # should print 49
