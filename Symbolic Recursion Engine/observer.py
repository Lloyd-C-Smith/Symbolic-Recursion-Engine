# observer.py
import random


class Observer:
    def __init__(self, label: str):
        self.label = label

    def context(self, memory):
        tops = memory.top_symbols(8)
        if not tops:
            return "void"

        if len(tops) >= 3 and random.random() < 0.55:
            return random.choice(tops[1:])[0]
        return random.choice(tops)[0]

    def allow(self, text: str) -> bool:
        return True