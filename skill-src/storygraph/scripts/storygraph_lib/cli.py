def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser(prog="storygraph")
    parser.add_argument("--version", action="store_true")
    args = parser.parse_args(argv)
    if args.version:
        print("storygraph 0.1.0")
    return 0
