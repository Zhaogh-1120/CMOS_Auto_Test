from e5052b_capture.client import E5052BClient


def main():
    client = E5052BClient().open()
    try:
        print("E5052B client placeholder opened.")
    finally:
        client.close()


if __name__ == "__main__":
    main()
