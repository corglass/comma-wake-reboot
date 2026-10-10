"""Debounce: require N consecutive frames >= threshold (openWakeWord 'patience' idea), output 1.0/0.0."""
class Patience:
    def __init__(self, threshold, patience):
        self.t, self.n, self.count = threshold, patience, 0
    def update(self, score):
        self.count = self.count + 1 if score >= self.t else 0
        if self.count >= self.n:
            self.count = 0
            return 1.0
        return 0.0
    def reset(self): self.count = 0
