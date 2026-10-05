"""Create a host-side Ollama alias retaining tools during multi-turn probing."""
import argparse
import subprocess
import tempfile
from pathlib import Path

from verify_local_tools import request


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", default="mistral-small3.2:24b")
    parser.add_argument("--alias", default="logiscope-mistral24-tools-probe")
    args = parser.parse_args()
    template = request("http://127.0.0.1:11434/api/show", {"model": args.source})["template"]
    old = "(le (len (slice $.Messages $index)) 2)"
    if template.count(old) != 1:
        raise SystemExit("Unexpected template: review before applying this adjustment")
    prefix = ('{{- $lastUserIndex := -1 -}}{{- range $i, $m := .Messages }}'
              '{{- if eq $m.Role "user" }}{{- $lastUserIndex = $i }}{{- end }}{{- end }}\n')
    adjusted = prefix + template.replace(old, "(eq $index $lastUserIndex)")
    with tempfile.TemporaryDirectory(prefix="logiscope-mistral-") as directory:
        path = Path(directory) / "Modelfile"
        path.write_text(f'FROM {args.source}\nPARAMETER num_ctx 8192\nTEMPLATE """{adjusted}"""\n')
        subprocess.run(["ollama", "create", args.alias, "-f", str(path)], check=True)


if __name__ == "__main__":
    main()
