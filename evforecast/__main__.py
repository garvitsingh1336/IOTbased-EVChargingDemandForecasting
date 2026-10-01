import argparse
import json
from .config import load_config
from .data import preprocess
from .evaluate import train, evaluate
from .replay import simulate

def main():
    parser = argparse.ArgumentParser(description="Local historical EV session-arrival forecasting.")
    parser.add_argument("command", choices=["preprocess", "train", "evaluate", "all", "simulate", "simulate-legacy", "bootstrap-db"])
    parser.add_argument("--config")
    parser.add_argument("--speed", type=float, default=3600, help="Historical seconds per real second")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--reset", action="store_true", help="Reset only the selected demo run")
    parser.add_argument("--api-url", default="http://127.0.0.1:8000")
    parser.add_argument("--run-id", default="demo")
    args = parser.parse_args()
    config = load_config(args.config)
    try:
        if args.command in ("preprocess", "all"):
            result = preprocess(config)
            print(json.dumps(result, indent=2, default=str))
        if args.command in ("train", "all"):
            result = train(config)
            print("Validation-selected model:", result["selected_model"])
        if args.command in ("evaluate", "all"):
            result = evaluate(config)
            print(json.dumps(result["test_metrics"], indent=2))
        if args.command == "bootstrap-db":
            from .bootstrap import bootstrap
            print(json.dumps(bootstrap(config), indent=2))
        if args.command == "simulate":
            from .replay_http import simulate_http
            simulate_http(config, args.api_url, args.run_id, args.speed, args.limit, args.reset)
        if args.command == "simulate-legacy":
            simulate(config, args.speed, args.limit, args.reset)
    except (FileNotFoundError, ValueError) as error:
        parser.exit(2, f"Error: {error}\n")

if __name__ == "__main__":
    main()
