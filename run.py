#!/usr/bin/env python3
"""
Run script for Curiosity Agent.
Usage: python run.py [--cli]
"""

import argparse
import asyncio
import os
import sys

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def check_api_key():
    """Verify API key is set."""
    if not os.environ.get("OPENROUTER_API_KEY"):
        print("❌ OPENROUTER_API_KEY not set!")
        print()
        print("Set it with:")
        print("  export OPENROUTER_API_KEY='your-key-here'")
        print()
        print("Get a free key at: https://openrouter.ai")
        sys.exit(1)


def run_web():
    """Run the web interface."""
    import uvicorn
    from app.server import app
    
    print("🔍 Starting Curiosity Agent Web Interface...")
    print("   Dashboard: http://127.0.0.1:8000")
    print()
    uvicorn.run(app, host="127.0.0.1", port=8000)


async def run_cli(max_iterations=None):
    """Run the agent in CLI mode."""
    from agent import CuriosityAgent
    
    print("🔍 Starting Curiosity Agent (CLI mode)...")
    print("   Press Ctrl+C to stop")
    print()
    
    agent = CuriosityAgent()
    
    try:
        await agent.run(max_iterations=max_iterations)
    except KeyboardInterrupt:
        print("\n⏹ Stopping agent...")
        agent.stop()


def main():
    parser = argparse.ArgumentParser(description="Run Curiosity Agent")
    parser.add_argument("--cli", action="store_true", help="Run in CLI mode (no web interface)")
    parser.add_argument("--iterations", type=int, help="Max iterations (CLI mode only)")
    args = parser.parse_args()
    
    check_api_key()
    
    if args.cli:
        asyncio.run(run_cli(max_iterations=args.iterations))
    else:
        run_web()


if __name__ == "__main__":
    main()
