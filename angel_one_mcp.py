"""Angel One CLI helper script for OpenCode integration."""
import sys
import json
from angel_one_client import manager

def main():
    if len(sys.argv) < 2:
        print("Usage: python angel_one_mcp.py <profile|holdings|positions>")
        sys.exit(1)
    
    cmd = sys.argv[1].lower()
    if cmd == "profile":
        print(json.dumps(manager.get_profile(), indent=2))
    elif cmd == "holdings":
        print(json.dumps(manager.get_holdings(), indent=2))
    elif cmd == "positions":
        print(json.dumps(manager.get_positions(), indent=2))
    else:
        print(f"Unknown command: {cmd}")

if __name__ == "__main__":
    main()
