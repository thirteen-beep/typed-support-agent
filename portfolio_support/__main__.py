import argparse
import json
from pathlib import Path
from .agent import run_support
from .store import Store

parser=argparse.ArgumentParser(description='Typed support agent using a real local Ollama model')
parser.add_argument('--database',type=Path,default=Path('.data/support.db'))
parser.add_argument('--question',default='What is the status of order A100?')
parser.add_argument('--tenant',default='acme')
parser.add_argument('--customer',default='alice')
parser.add_argument('--session',default='cli-demo')
args=parser.parse_args()
store=Store(args.database)
store.seed_demo()
print(json.dumps(run_support(args.question,store=store,tenant=args.tenant,customer=args.customer,session_id=args.session),ensure_ascii=False,indent=2))
