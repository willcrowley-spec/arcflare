from antlr4 import CommonTokenStream
from antlr4.error.ErrorListener import ErrorListener

from app.services.salesforce.apex_parser import CaseInsensitiveInputStream
from app.services.salesforce.apex_parser.ApexLexer import ApexLexer
from app.services.salesforce.apex_parser.ApexParser import ApexParser


class _ThrowingErrorListener(ErrorListener):
    def syntaxError(self, recognizer, offendingSymbol, line, column, msg, e):
        raise SyntaxError(f"line {line}:{column} {msg}")


def test_parse_minimal_class_no_errors():
    src = "public class HelloWorld {\n}\n"
    lexer = ApexLexer(CaseInsensitiveInputStream(src))
    stream = CommonTokenStream(lexer)
    parser = ApexParser(stream)
    parser.removeErrorListeners()
    parser.addErrorListener(_ThrowingErrorListener())
    tree = parser.compilationUnit()
    assert tree is not None
    assert stream.tokens[-1].type == ApexParser.EOF
