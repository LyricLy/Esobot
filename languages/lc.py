import asyncio
from enum import Enum, auto
from functools import reduce

display_name = "λ - Lambda Calculus"
hello_world = "(\\nm.\\fx.n f (m f x)) (\\fx.f x) (\\fx.f (f x))"


async def interpret(program, _, __, stdout):
    try:
        await stdout.write(parse(lex(program), []).simpl().pretty([]))
    except RecursionError as err:
        await stdout.write(parse(lex(program), []).pretty([]))
    except Exception as err:
        await stdout.write(f"{type(err).__name__}: {str(err)}")

class Expr_Type(Enum):
    var = auto()
    apply = auto()
    func = auto()
    symbol = auto()

class Expr():
    def simpl(self): pass
    def eq(self, other): pass # Check if two expressions are equal.
    def pretty(self): pass # Turn expression into string.
    def replace(self, arg, depth): pass # Replace variable in expression.
    
    # When replacing a variable, adapt the de Bruijn index of argument passed.
    def adapt_depth(self, replacement_depth, depth): pass

class Var(Expr):
    def __init__(self, num):
        self.type = Expr_Type.var
        self.num = num
    
    def simpl(self): return self
    def eq(self, other): return other.type == Expr_Type.var and self.num == other.num
    def pretty(self, vars): return vars[-self.num-1] if len(vars) >= self.num + 1 else self.num
    def tojson(self): return f'{{"num": {self.num}}}'
    
    def replace(self, arg, depth):
        if self.num == depth:
            return arg.adapt_depth(depth, 0)
        elif self.num > depth:
            return Var(self.num - 1)
        else:
            return self
    
    def adapt_depth(self, replacement_depth, depth):
        if self.num >= depth:
            return Var(self.num + replacement_depth)
        else:
            return self

class Apply(Expr):
    def __init__(self, func, arg):
        self.type = Expr_Type.apply
        self.func = func
        self.arg = arg
    
    def simpl(self):
        old = Var(0)
        new = self
        
        while not old.eq(new):
            if new.type == Expr_Type.apply:
                if new.func.type == Expr_Type.func:
                    old = new
                    new = new.func.apply(new.arg)
                else:
                    old = new
                    new = Apply(new.func.simpl(), new.arg.simpl())
            else:
                old = new
                new = new.simpl()
        
        return new
    
    def eq(self, other): return (
        other.type == Expr_Type.apply and
        self.func.eq(other.func) and
        self.arg.eq(other.arg))
    
    def pretty(self, vars):
        arg = self.arg.pretty(vars)
        if self.arg.type == Expr_Type.apply:
            arg = f"({arg})"
        return f"{self.func.pretty(vars)} {arg}"
    
    def tojson(self):
        return f'{{"func": {self.func.tojson()}, "arg": {self.arg.tojson()}}}'
    
    def replace(self, arg, depth):
        return Apply(
            self.func.replace(arg, depth),
            self.arg.replace(arg, depth))
    
    def adapt_depth(self, replacement_depth, depth):
        return Apply(
            self.func.adapt_depth(replacement_depth, depth),
            self.arg.adapt_depth(replacement_depth, depth))

class Func(Expr):
    def __init__(self, arg, body):
        self.type = Expr_Type.func
        self.arg = arg # For turning back into text.
        self.body = body
    
    def simpl(self): return Func(self.arg, self.body.simpl())
    
    def eq(self, other): return other.type == Expr_Type.func and self.body.eq(other.body)
    
    def pretty(self, vars):
        arg = self.arg
        body = self.body.pretty(vars + [arg])
        if self.body.type == Expr_Type.func:
            body = body[2:-1]
            arg += " "
        else:
            arg += "."
        return f"(λ{arg}{body})"
    
    def tojson(self):
        return f'{{"arg": {self.arg}, "body": {self.body.tojson()}}}'
    
    def apply(self, arg): return self.body.replace(arg, 0)
    
    def replace(self, arg, depth):
        return Func(self.arg, self.body.replace(arg, depth + 1))
    
    def adapt_depth(self, replacement_depth, depth):
        return Func(self.arg, self.body.adapt_depth(replacement_depth, depth + 1))

class Symbol(Expr):
    def __init__(self, name):
        self.type = Expr_Type.symbol
        self.name = name
    
    def simpl(self): return self
    def eq(self, other): return other.type == Expr_Type.symbol and self.name == other.name
    def pretty(self, vars): return self.name
    def tojson(self): return f'{{"name": {self.name}}}'
    def replace(self, arg, depth): return self
    def adapt_depth(self, replacement_depth, depth): return self

class Token(Enum):
    lambda_ = auto()
    dot = auto()
    open_parens = auto()
    close_parens = auto()
    symbol = auto()

def lex(prog):
    tokens = []
    i = 0
    while i < len(prog):
        char = prog[i]
        if char == "\\" or char == "λ":
            tokens.append((Token.lambda_, None))
        elif char == ".":
            tokens.append((Token.dot, None))
        elif char == "(":
            tokens.append((Token.open_parens, None))
        elif char == ")":
            tokens.append((Token.close_parens, None))
        elif not char.isspace():
            name = char
            i += 1
            while (
                i < len(prog) and
                not prog[i].isspace() and
                prog[i] != "\\" and prog[i] != "λ" and
                prog[i] != "." and
                prog[i] != "(" and prog[i] != ")"):
                name += prog[i]
                i += 1
            i -= 1
            tokens.append((Token.symbol, name))
        i += 1
    return tokens

type_ = 0
name_ = 1

class ParseError(Exception):
    pass

def parse(tokens, vars):
    if len(tokens) == 0:
        raise ParseError("Cannot run empty program or empty parenthesis.")
    
    if tokens[0][type_] == Token.lambda_:
        args = []
        i = 1
        while i < len(tokens) and tokens[i][type_] == Token.symbol:
            args.append(tokens[i][name_])
            i += 1
        
        if len(args) <= 0:
            raise ParseError("There is a lambda without arguments.")
        if (
            i >= len(tokens) or
            tokens[i][type_] != Token.dot):
            raise ParseError("There is a lambda without a dot separating the arguments from the body.")
        if i + 1 >= len(tokens):
            raise ParseError("There is a lambda without a body to run.")
        
        body = parse(tokens[i+1:], vars + args)
        func = reduce(
            lambda body, arg: Func(arg, body),
            reversed(args),
            body)
        return func
    else:
        terms = []
        depth = 0
        for i, token in enumerate(tokens):
            token_type = token[type_]
            
            if token_type == Token.open_parens:
                if depth == 0:
                    begin = i
                depth += 1
            
            elif token_type == Token.close_parens:
                depth -= 1
                if depth < 0:
                    raise ParseError("Unmatched `)`.")
                if depth == 0:
                    terms.append(parse(tokens[begin+1:i], vars))
            
            elif depth == 0:
                if token_type == Token.symbol:
                    name = token[name_]
                    if name in vars:
                        num = list(reversed(vars)).index(name)
                        terms.append(Var(num))
                    else:
                        terms.append(Symbol(name))
                
                elif token_type == Token.lambda_:
                    terms.append(parse(tokens[i:], vars))
                    break
                elif token_type == Token.dot:
                    raise ParseError("Dot found not used in lambda.")
        
        if depth > 0:
            raise ParseError("Unmatched `(`.")
        
        if len(terms) == 0:
            return terms[0]
        else:
            return reduce(Apply, terms)