import re

text1 = "<edit>test</edit>"
print(bool(re.search(r"<edit>(.*?)</edit>", text1, re.DOTALL | re.IGNORECASE)))

text2 = "\<edit\>test\</edit\>"
print(bool(re.search(r"<edit>(.*?)</edit>", text2, re.DOTALL | re.IGNORECASE)))

text3 = "< edit >test< /edit >"
print(bool(re.search(r"<edit>(.*?)</edit>", text3, re.DOTALL | re.IGNORECASE)))