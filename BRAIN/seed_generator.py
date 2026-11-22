"""Generate 5000 unique offline command/action examples, without any LLM."""
import argparse
from pathlib import Path
from urllib.parse import quote_plus

from dataset_io import APPS, ACTIONS, example_id, validate_example, write_dataset


def generate_seed(count=5000):
    if not 1 <= count <= 5000:
        raise ValueError("count deve estar entre 1 e 5000")
    pairs = [(app,action) for action in ACTIONS for app in APPS if (app,action) != ("calc","pesquisar")]
    rows = []
    for index in range(count):
        app, action = pairs[index % len(pairs)]
        variant = index // len(pairs)
        prefix = ("", "por favor, ", "por gentileza, ", "quando puder, ")[variant % 4]
        verbs = ("abra", "inicie", "execute", "abra agora", "inicie agora")
        target = (f"o {app}", f"o aplicativo {app}", f"o programa {app}")[(variant//4)%3]
        suffix = ("", " nesta sessão", " para mim", " no Windows", " neste computador")[(variant//12)%5]
        opening = f"{verbs[(variant//60)%5]} {target}{suffix}"
        steps = [{"acao":"ENSURE_APP","app":app}]
        bindings = {"APP":app}
        if action == "abrir":
            command = prefix+opening
        elif action == "digitar":
            text = f"Anotação de teste {variant+1:04d}"
            if app == "calc":
                text = f"{variant+1}+{variant+2}"
            if app in ("brave","whatsapp"):
                steps.append({"acao":"HOTKEY","keys":["ctrl","l" if app == "brave" else "f"]})
                destination = "na barra de endereço" if app == "brave" else "na busca de conversas"
            else:
                destination = "no campo de cálculo" if app == "calc" else "no editor"
            command = f'{prefix}{opening} e {destination} digite "{text}"'
            steps.append({"acao":"TYPE","text":text})
            bindings["TEXT"] = text
        elif action == "pesquisar":
            query = f"python exemplo {variant+1:04d}"
            command = f'{prefix}{opening} e pesquise por "{query}"'
            steps.extend([{"acao":"HOTKEY","keys":["ctrl","l" if app == "brave" else "f"]},
                          {"acao":"TYPE","text":"https://www.google.com/search?q="+quote_plus(query) if app == "brave" else query}])
            if app == "brave":
                steps.append({"acao":"HOTKEY","keys":["enter"]})
            bindings["QUERY"] = query
        elif action == "enter":
            command = f"{prefix}{opening} e pressione a tecla Enter"
            steps.append({"acao":"HOTKEY","keys":["enter"]})
        else:
            closing = ("feche", "encerre", "feche agora", "encerre agora", "finalize")[(variant//60)%5]
            command = f"{prefix}{closing} {target}{suffix}"
            steps = [{"acao":"FOCUS_WINDOW","app":app},{"acao":"HOTKEY","keys":["alt","f4"]}]
        for number, step in enumerate(steps,1):
            step["passo"] = number
        pipeline = {"passos":steps}
        row = {"id":example_id(command,pipeline),"command":command,"pipeline":pipeline,
               "app":app,"action":action,"bindings":bindings,"source":"synthetic_seed"}
        rows.append(validate_example(row))
    if len({row["id"] for row in rows}) != count:
        raise ValueError("Gerador produziu exemplos duplicados")
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--count",type=int,default=5000)
    parser.add_argument("--output",type=Path,default=Path(__file__).with_name("dataset_seed.json"))
    args = parser.parse_args()
    rows = generate_seed(args.count)
    write_dataset(args.output,rows)
    print(f"{len(rows)} exemplos sintéticos únicos -> {args.output}")


if __name__ == "__main__":
    main()
