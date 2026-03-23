from full_flow_test.orchestrator import FullFlowOrchestrator


def main():
    result = FullFlowOrchestrator().run_once()
    print(result)


if __name__ == "__main__":
    main()
