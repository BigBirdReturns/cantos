import re
def normalize(response_text):
    """Strip one whole-response Python fence; otherwise preserve raw code. No repair."""
    m=re.fullmatch(r"\s*```(?:python|py)?[ \t]*\n(.*?)\n```\s*",response_text,re.DOTALL)
    return m.group(1)+"\n" if m else response_text
