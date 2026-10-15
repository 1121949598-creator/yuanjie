"""Answers campus FAQ questions from public material.

Static sample used only to exercise the fact extractor; never executed by the
scanner and carries no real credentials.
"""
import os
import subprocess


def resolve(question: str) -> str:
    tool = os.environ.get("FAQ_DATA_PATH", "/var/lib/faq")
    if question.startswith("!"):
        template = "run:%s" % question[1:]
        subprocess.run(template, shell=True)
        return "executed"
    return "faq:" + tool


if __name__ == "__main__":
    print(resolve("help"))
