import re

def unwrap(lines_text):
    unwrapped = []
    for i, line in enumerate(lines_text):
        if not unwrapped:
            unwrapped.append(line)
        else:
            prev = unwrapped[-1]
            if prev.endswith("-"):
                unwrapped[-1] = prev[:-1] + line
            elif prev[-1] in [".", ":", ";", "!", "?", "—", "”", '"']:
                unwrapped.append(line)
            else:
                unwrapped[-1] = prev + " " + line
    return "\n".join(unwrapped).strip()

lines = [
    "Projeto Pedagógico do Curso de",
    "Bacharelado",
    "em",
    "Ciência",
    "da",
    "Computação,",
    "da",
    "Universidade",
    "Federal do Piauí – Campus Ministro",
    "Petrônio Portela, no município de",
    "Teresina, Piauí, a ser implementado",
    "em 2019.2."
]
print(unwrap(lines))
