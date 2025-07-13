from glob import iglob
from os import path


def get_extensions():
    extensions_list = []
    d = path.dirname(__file__)
    for filepath in iglob(path.join(d, "**/*.py"), recursive=True):
        if path.basename(filepath).startswith("_"):
            continue
        filename = path.relpath(filepath, d)
        extensions_list.append(filename.removesuffix(".py").replace("/", "."))
    return extensions_list
