import re

def parse_response(text: str):
    edit_content = None
    comment = None
    
    edit_match = re.search(r"<edit>(.*?)</edit>", text, re.DOTALL | re.IGNORECASE)
    if edit_match:
        edit_content = edit_match.group(1).strip()
        
    comment_match = re.search(r"<comment>(.*?)</comment>", text, re.DOTALL | re.IGNORECASE)
    if comment_match:
        comment = comment_match.group(1).strip()
        
    return edit_content, comment

responses = [
    """<edit>
# Titre du doc
Voici le contenu.
Avec un saut de ligne.
</edit>
<comment>
J'ai mis a jour le doc !
</comment>""",
    """Voici le document mis a jour:
<edit>
Juste ca.
</edit>
N'hesite pas si tu as d'autres requetes !""",
    """<comment>Je n'ai pas le droit de modifier ces donnees privees.</comment>""",
    """Une reponse totalement normale sans balises."""
]

for i, r in enumerate(responses):
    print(f"\n--- TEST {i+1} ---")
    e, c = parse_response(r)
    if not e and not c:
        print("RESULT: Fallback (Chat brut)")
    else:
        print(f"EDIT: {repr(e)}")
        print(f"COMMENT: {repr(c)}")