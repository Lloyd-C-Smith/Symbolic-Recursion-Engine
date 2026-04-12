# io_handler.py
import time


def log(msg, color=None):
    ts = time.strftime("%H:%M:%S")
    print(f"[{ts}] {msg}")


def divider(ch="="):
    print(ch * 60)


def show_summary(data):
    log("Summary")
    for key, value in data.items():
        print(f" - {key}: {value}")