"""Multi-requirement BUILD eval (EXT-009 / REQ-6, build variant): measure the jarify-flow's
decomposition on MULTI-FUNCTION builds — where free-form / single-function generation can't reach.

Each scenario is a high-level intent naming several functions. `spec_driven_loop` decomposes it
into requirements, writes a test per requirement, implements, and verifies. We then score against
a HIDDEN ORACLE (a held-out test the system never saw) exercising ALL functions — the un-gameable
"did it meet intent" measure (the EXT-008 pattern). Records suite="build" to the trend history.
"""
from __future__ import annotations

import subprocess
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

from harness.eval_runner import MODEL, _persist
from harness.report import census

# #EXT-009-REQ-6 Start
SCENARIOS = [
    {
        "name": "calculator",
        "intent": "a math module with a function add(a, b) that adds, subtract(a, b) that "
                  "subtracts the second from the first, and multiply(a, b) that multiplies",
        "oracle": ("from solution import add, subtract, multiply\n\n"
                   "def test_all():\n"
                   "    assert add(2, 3) == 5\n"
                   "    assert subtract(5, 2) == 3\n"
                   "    assert multiply(4, 6) == 24\n"),
    },
    {
        "name": "stringops",
        "intent": "a string module with reverse(s) that reverses a string, shout(s) that returns "
                  "it uppercased, and vowel_count(s) that counts the vowels",
        "oracle": ("from solution import reverse, shout, vowel_count\n\n"
                   "def test_all():\n"
                   "    assert reverse('abc') == 'cba'\n"
                   "    assert shout('hi') == 'HI'\n"
                   "    assert vowel_count('hello') == 2\n"),
    },
    {
        "name": "listops",
        "intent": "a list module with largest(xs) returning the max, smallest(xs) returning the "
                  "min, and total(xs) returning the sum",
        "oracle": ("from solution import largest, smallest, total\n\n"
                   "def test_all():\n"
                   "    assert largest([1, 5, 2]) == 5\n"
                   "    assert smallest([3, 1, 2]) == 1\n"
                   "    assert total([1, 2, 3]) == 6\n"),
    },
    {
        "name": "boolchecks",
        "intent": "a number module with is_even(n) returning True when n is even, is_odd(n) "
                  "returning True when n is odd, and is_positive(n) returning True when n > 0",
        "oracle": ("from solution import is_even, is_odd, is_positive\n\n"
                   "def test_all():\n"
                   "    assert is_even(4) is True and is_even(3) is False\n"
                   "    assert is_odd(3) is True and is_odd(4) is False\n"
                   "    assert is_positive(5) is True and is_positive(-1) is False\n"),
    },
    {
        "name": "tempconvert",
        "intent": "a temperature module with c_to_f(c) converting Celsius to Fahrenheit, and "
                  "f_to_c(f) converting Fahrenheit to Celsius",
        "oracle": ("from solution import c_to_f, f_to_c\n\n"
                   "def test_all():\n"
                   "    assert c_to_f(0) == 32\n"
                   "    assert c_to_f(100) == 212\n"
                   "    assert f_to_c(32) == 0\n"),
    },
    {
        "name": "textstats",
        "intent": "a text module with word_count(s) returning the number of words, char_count(s) "
                  "returning the number of characters, and shout(s) returning s uppercased",
        "oracle": ("from solution import word_count, char_count, shout\n\n"
                   "def test_all():\n"
                   "    assert word_count('a b c') == 3\n"
                   "    assert char_count('abc') == 3\n"
                   "    assert shout('hi') == 'HI'\n"),
    },
    {
        "name": "minmax",
        "intent": "a module with maximum(xs) returning the largest item in a list and minimum(xs) "
                  "returning the smallest item in a list",
        "oracle": ("from solution import maximum, minimum\n\n"
                   "def test_all():\n"
                   "    assert maximum([1, 5, 2]) == 5\n"
                   "    assert minimum([3, 1, 2]) == 1\n"),
    },
]

# HARDER, UNSATURATED tier (find the real ceiling past the saturated easy 7/7): conditional/None
# handling, multi-branch + string conversion, real algorithms (Euclid), composition, parsing.
HARD_SCENARIOS = [
    {
        "name": "safe_math",
        "intent": "a math module with safe_divide(a, b) returning a / b but None when b is 0, and "
                  "percent(part, whole) returning part / whole * 100 but 0 when whole is 0",
        "oracle": ("from solution import safe_divide, percent\n\n"
                   "def test_all():\n"
                   "    assert safe_divide(6, 2) == 3\n"
                   "    assert safe_divide(1, 0) is None\n"
                   "    assert percent(1, 4) == 25\n"
                   "    assert percent(1, 0) == 0\n"),
    },
    {
        "name": "fizzbuzz_leap",
        "intent": "a module with fizzbuzz(n) returning 'Fizz' if n is divisible by 3, 'Buzz' if by 5, "
                  "'FizzBuzz' if divisible by both, otherwise the number as a string; and "
                  "is_leap(year) returning True for leap years",
        "oracle": ("from solution import fizzbuzz, is_leap\n\n"
                   "def test_all():\n"
                   "    assert fizzbuzz(3) == 'Fizz'\n"
                   "    assert fizzbuzz(5) == 'Buzz'\n"
                   "    assert fizzbuzz(15) == 'FizzBuzz'\n"
                   "    assert fizzbuzz(7) == '7'\n"
                   "    assert is_leap(2020) is True and is_leap(1900) is False\n"),
    },
    {
        "name": "gcd_lcm",
        "intent": "a math module with gcd(a, b) returning the greatest common divisor and "
                  "lcm(a, b) returning the least common multiple of a and b",
        "oracle": ("from solution import gcd, lcm\n\n"
                   "def test_all():\n"
                   "    assert gcd(12, 8) == 4\n"
                   "    assert gcd(7, 13) == 1\n"
                   "    assert lcm(4, 6) == 12\n"),
    },
    {
        "name": "stats",
        "intent": "a stats module with mean(xs) returning the average, median(xs) returning the "
                  "middle value of the sorted list, and mode(xs) returning the most common value",
        "oracle": ("from solution import mean, median, mode\n\n"
                   "def test_all():\n"
                   "    assert mean([1, 2, 3]) == 2\n"
                   "    assert median([3, 1, 2]) == 2\n"
                   "    assert mode([1, 1, 2]) == 1\n"),
    },
    {
        "name": "stringparse",
        "intent": "a text module with initials(name) returning the uppercase initials of each word, "
                  "and slugify(s) returning the string lowercased with spaces replaced by dashes",
        "oracle": ("from solution import initials, slugify\n\n"
                   "def test_all():\n"
                   "    assert initials('john doe') == 'JD'\n"
                   "    assert slugify('Hello World') == 'hello-world'\n"),
    },
]


def _oracle_pass(solution_code: str, oracle_test: str) -> bool:
    """Score in a FRESH dir (the system never saw the oracle) — un-gameable intent check."""
    if not solution_code.strip():
        return False
    with tempfile.TemporaryDirectory() as od:
        (Path(od) / "solution.py").write_text(solution_code, encoding="utf-8", newline="\n")
        (Path(od) / "test_oracle.py").write_text(oracle_test, encoding="utf-8", newline="\n")
        try:
            return subprocess.run("python -m pytest -q test_oracle.py", cwd=od, shell=True,
                                  capture_output=True, text=True, timeout=60).returncode == 0
        except Exception:
            return False


def run_build_eval(verbose: bool = False, persist: bool = True,
                   scenarios: list | None = None, suite: str = "build") -> dict:
    """Run the decompose BUILD flow on each multi-function intent; score against the hidden oracle."""
    from harness.spec_loop import spec_driven_loop
    scenarios = SCENARIOS if scenarios is None else scenarios
    started = time.time()
    results = []
    for sc in scenarios:
        with tempfile.TemporaryDirectory() as d:
            spec_driven_loop(sc["intent"], d, verbose=verbose)
            sol = Path(d) / "solution.py"
            ok = _oracle_pass(sol.read_text(encoding="utf-8") if sol.is_file() else "", sc["oracle"])
            results.append({"name": sc["name"], "solved": ok})
            print(f"  {'PASS' if ok else 'FAIL'} {sc['name']}", flush=True)
    solved, total = sum(1 for r in results if r["solved"]), len(results)
    print(f"\n=== {suite} eval (oracle-scored): {solved}/{total} = {solved / total * 100:.0f}% ===")
    scorecard = {
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "suite": suite, "model": MODEL,
        "passRate": round(solved / total, 4) if total else 0.0,
        "solved": solved, "total": total, "elapsedSec": round(time.time() - started, 1),
        "census": census(), "perTask": results,
    }
    if persist:
        _persist(scorecard)
    return scorecard


def run_build_eval_hard(verbose: bool = False, persist: bool = True) -> dict:
    """The HARDER, unsaturated tier (suite='build-hard'): error/None handling, multi-branch + string
    conversion, real algorithms (Euclid), composition, parsing — find the build flow's real ceiling
    past the saturated easy 7/7. Drive improvement against THIS, not the maxed easy tier."""
    return run_build_eval(verbose=verbose, persist=persist,
                          scenarios=HARD_SCENARIOS, suite="build-hard")


# CLASS/OOP builds (suite='build-class') — a NEW capability CLASS beyond standalone functions.
# Probe finding: the 2B writes classes fine and the flow's whole-file path already emits a correct
# class; the win was stripping the '>>>FILE' output artifact (_sanitize_source).
CLASS_SCENARIOS = [
    {
        "name": "stack",
        "intent": "a Stack class with push(x) to add an item, pop() returning and removing the last "
                  "item, and is_empty() returning True when empty",
        "oracle": ("from solution import Stack\n\n"
                   "def test_all():\n"
                   "    s = Stack()\n"
                   "    assert s.is_empty() is True\n"
                   "    s.push(1); s.push(2)\n"
                   "    assert s.pop() == 2\n"
                   "    assert s.is_empty() is False\n"),
    },
    {
        "name": "counter",
        "intent": "a Counter class with increment() to add one, value() returning the current count "
                  "starting at 0, and reset() setting it back to 0",
        "oracle": ("from solution import Counter\n\n"
                   "def test_all():\n"
                   "    c = Counter()\n"
                   "    assert c.value() == 0\n"
                   "    c.increment(); c.increment()\n"
                   "    assert c.value() == 2\n"
                   "    c.reset()\n"
                   "    assert c.value() == 0\n"),
    },
    {
        # Known-hard (build-class 3/4): the 2B names the attribute `self.balance` AND the method
        # `balance()` the same -> the instance attribute shadows the method -> `a.balance()` calls an
        # int (TypeError). A genuine model-judgement gotcha (not an artifact), kept as the honest 4th.
        "name": "bankaccount",
        "intent": "a BankAccount class starting at balance 0 with deposit(amount), withdraw(amount), "
                  "and balance() returning the current balance",
        "oracle": ("from solution import BankAccount\n\n"
                   "def test_all():\n"
                   "    a = BankAccount()\n"
                   "    a.deposit(100)\n"
                   "    a.withdraw(30)\n"
                   "    assert a.balance() == 70\n"),
    },
    {
        "name": "rectangle",
        "intent": "a Rectangle class created with width and height, with area() returning "
                  "width * height and perimeter() returning 2 * (width + height)",
        "oracle": ("from solution import Rectangle\n\n"
                   "def test_all():\n"
                   "    r = Rectangle(3, 4)\n"
                   "    assert r.area() == 12\n"
                   "    assert r.perimeter() == 14\n"),
    },
    {   # FIFO (vs Stack's LIFO)
        "name": "queue",
        "intent": "a Queue class with enqueue(x) to add an item, dequeue() returning and removing "
                  "the FIRST item added, and size() returning how many items are queued",
        "oracle": ("from solution import Queue\n\n"
                   "def test_all():\n"
                   "    q = Queue()\n"
                   "    q.enqueue(1); q.enqueue(2)\n"
                   "    assert q.dequeue() == 1\n"
                   "    assert q.size() == 1\n"),
    },
    {   # running aggregation state
        "name": "accumulator",
        "intent": "an Accumulator class with add(x) to add a number to a running total, total() "
                  "returning the sum so far, and count() returning how many numbers were added",
        "oracle": ("from solution import Accumulator\n\n"
                   "def test_all():\n"
                   "    a = Accumulator()\n"
                   "    a.add(5); a.add(3)\n"
                   "    assert a.total() == 8\n"
                   "    assert a.count() == 2\n"),
    },
    {   # constructor arg + conversion + predicate
        "name": "temperature",
        "intent": "a Temperature class created with a celsius value, with to_fahrenheit() returning "
                  "the Fahrenheit value and freezing() returning True when celsius is 0 or below",
        "oracle": ("from solution import Temperature\n\n"
                   "def test_all():\n"
                   "    assert Temperature(0).to_fahrenheit() == 32\n"
                   "    assert Temperature(100).to_fahrenheit() == 212\n"
                   "    assert Temperature(0).freezing() is True\n"
                   "    assert Temperature(10).freezing() is False\n"),
    },
    {   # dict-backed counting state
        "name": "wordbag",
        "intent": "a WordBag class with add(word) to record a word, count(word) returning how many "
                  "times that word was added, and unique() returning the number of distinct words",
        "oracle": ("from solution import WordBag\n\n"
                   "def test_all():\n"
                   "    w = WordBag()\n"
                   "    w.add('a'); w.add('a'); w.add('b')\n"
                   "    assert w.count('a') == 2\n"
                   "    assert w.unique() == 2\n"),
    },
]


def run_class_eval(verbose: bool = False, persist: bool = True) -> dict:
    """Class/OOP builds (suite='build-class') — the NEW capability class: stateful objects with
    methods, beyond standalone functions. Same hidden-oracle scoring (instantiate + exercise)."""
    return run_build_eval(verbose=verbose, persist=persist,
                          scenarios=CLASS_SCENARIOS, suite="build-class")
# #EXT-009-REQ-6 End


if __name__ == "__main__":
    import sys
    (run_build_eval_hard if "--hard" in sys.argv else run_build_eval)(verbose=True)
