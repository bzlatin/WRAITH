"""Accept a JSON request on stdin, or ask a question without Wraith."""

import argparse
import json
import sys
from .agent import evaluate

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--question")
parser.add_argument("--audience", choices=["public", "staff"], default="public")
parser.add_argument("--customer", default="alice")
parser.add_argument("--order-id", default="A100")
args = parser.parse_args()
payload = (
    {
        "question": args.question,
        "audience": args.audience,
        "customer": args.customer,
        "order_id": args.order_id,
    }
    if args.question
    else json.load(sys.stdin)
)
print(json.dumps(evaluate(payload)))
