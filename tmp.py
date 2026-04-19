import re
text = open('templates/users.html', encoding='utf-8').read()
old = re.findall(r'<span class=\"badge badge-\$\{u\.role.*?</span>', text, re.DOTALL)
if old:
    old_str = old[0]
    print('Found:', old_str)
    new_str = old_str + '\n' + r'''                                  <span class="badge" style="font-size:0.65rem; background: ; color: ; margin-left: var(--space-xs);"></span>'''
    text = text.replace(old_str, new_str)
    open('templates/users.html', 'w', encoding='utf-8').write(text)
    print('Replaced')
