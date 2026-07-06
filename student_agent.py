import re
from collections import deque

# ============ PARSEO DEL ENUNCIADO ============

def get_last_statement_block(scenario_context: str) -> str:
    return scenario_context.split('[STATEMENT]')[-1]

def detect_domain(scenario_context: str) -> str:
    return 'blocksworld' if 'mount_nodes' in scenario_context else 'craves'

def split_clauses(sentence: str):
    sentence = sentence.strip().rstrip('.')
    sentence = sentence.replace(' and ', ', ')
    return [p.strip() for p in sentence.split(',') if p.strip()]

def parse_blocksworld_facts(clauses):
    facts = set()
    for c in clauses:
        m = re.match(r'the (\w+) block is unobstructed', c)
        if m: facts.add(('clear', m.group(1))); continue
        if re.match(r'the hand is empty', c): facts.add(('handempty',)); continue
        m = re.match(r'the (\w+) block is on top of the (\w+) block', c)
        if m: facts.add(('on', m.group(1), m.group(2))); continue
        m = re.match(r'the (\w+) block is on the table', c)
        if m: facts.add(('ontable', m.group(1))); continue
        m = re.match(r'the hand is holding the (\w+) block', c)
        if m: facts.add(('holding', m.group(1))); continue
    return facts

def parse_craves_facts(clauses):
    facts = set()
    for c in clauses:
        if c == 'harmony': facts.add(('harmony',)); continue
        m = re.match(r'object (\w+) craves object (\w+)', c)
        if m: facts.add(('craves', m.group(1), m.group(2))); continue
        m = re.match(r'planet object (\w+)', c)
        if m: facts.add(('planet', m.group(1))); continue
        m = re.match(r'province object (\w+)', c)
        if m: facts.add(('province', m.group(1))); continue
        m = re.match(r'pain object (\w+)', c)
        if m: facts.add(('pain', m.group(1))); continue
    return facts

def parse_problem(scenario_context: str):
    domain = detect_domain(scenario_context)
    block = get_last_statement_block(scenario_context)

    init_m = re.search(r'As initial conditions I have that,?\s*(.*?)\s*My goal', block, re.S)
    goal_m = re.search(r'My goal is to have that\s*(.*?)\s*My plan', block, re.S)
    init_clauses = split_clauses(init_m.group(1) if init_m else "")
    goal_clauses = split_clauses(goal_m.group(1) if goal_m else "")

    parser = parse_blocksworld_facts if domain == 'blocksworld' else parse_craves_facts
    init_state = parser(init_clauses)
    goal_state = parser(goal_clauses)

    objects = set()
    for f in init_state | goal_state:
        objects.update(f[1:])
    return domain, init_state, goal_state, sorted(objects)

# ============ MODELOS DE ACCIONES (STRIPS) ============

def blocksworld_actions(objects):
    A = []
    for x in objects:
        A.append(('pickup', (x,), {('ontable', x), ('clear', x), ('handempty',)},
                  {('holding', x)}, {('ontable', x), ('clear', x), ('handempty',)}))
        A.append(('putdown', (x,), {('holding', x)},
                  {('ontable', x), ('clear', x), ('handempty',)}, {('holding', x)}))
    for x in objects:
        for y in objects:
            if x == y: continue
            A.append(('stack', (x, y), {('holding', x), ('clear', y)},
                      {('on', x, y), ('clear', x), ('handempty',)}, {('holding', x), ('clear', y)}))
            A.append(('unstack', (x, y), {('on', x, y), ('clear', x), ('handempty',)},
                      {('holding', x), ('clear', y)}, {('on', x, y), ('clear', x), ('handempty',)}))
    return A

def craves_actions(objects):
    A = []
    for x in objects:
        A.append(('attack', (x,), {('province', x), ('planet', x), ('harmony',)},
                  {('pain', x)}, {('province', x), ('planet', x), ('harmony',)}))
        A.append(('succumb', (x,), {('pain', x)},
                  {('province', x), ('planet', x), ('harmony',)}, {('pain', x)}))
    for x in objects:
        for y in objects:
            if x == y: continue
            A.append(('overcome', (x, y), {('province', y), ('pain', x)},
                      {('harmony',), ('province', x), ('craves', x, y)}, {('province', y), ('pain', x)}))
            A.append(('feast', (x, y), {('craves', x, y), ('province', x), ('harmony',)},
                      {('pain', x), ('province', y)}, {('craves', x, y), ('province', x), ('harmony',)}))
    return A

ACTIONS_FN = {'blocksworld': blocksworld_actions, 'craves': craves_actions}
CODE_MAP = {
    'blocksworld': {'pickup': 'engage_payload', 'putdown': 'release_payload',
                     'stack': 'mount_node', 'unstack': 'unmount_node'},
    'craves': {'attack': 'attack', 'succumb': 'succumb', 'overcome': 'overcome', 'feast': 'feast'}
}

# ============ SOLVER SIMBOLICO (BFS, plan optimo garantizado) ============

def bfs_plan(init_state, goal_state, actions, max_depth=12):
    init_state, goal_state = frozenset(init_state), frozenset(goal_state)
    if goal_state.issubset(init_state):
        return []
    visited = {init_state}
    queue = deque([(init_state, [])])
    while queue:
        state, path = queue.popleft()
        if len(path) >= max_depth:
            continue
        for name, args, pre, add, rem in actions:
            if pre.issubset(state):
                new_state = frozenset((state - rem) | add)
                if new_state in visited:
                    continue
                new_path = path + [(name, args)]
                if goal_state.issubset(new_state):
                    return new_path
                visited.add(new_state)
                queue.append((new_state, new_path))
    return None

def format_plan(domain, plan):
    code_map = CODE_MAP[domain]
    return [f"({code_map[name]} {' '.join(args)})" for name, args in plan]

# ============ AGENTE ============

class AssemblyAgent:
    def __init__(self):
        self.bw_example = (
            "Ejemplo (dominio bloques):\n"
            "Inicial: red unobstructed, blue unobstructed, orange unobstructed, hand empty, "
            "red on table, blue on table, orange on table.\n"
            "Meta: red on top of orange, blue on top of red.\n"
            "[PLAN]\n(engage_payload red)\n(mount_node red orange)\n"
            "(engage_payload blue)\n(mount_node blue red)\n[PLAN END]\n"
        )
        self.cr_example = (
            "Ejemplo (dominio objetos):\n"
            "Inicial: harmony, planet a, planet b, planet c, province a, province b, province c.\n"
            "Meta: a craves c, b craves a.\n"
            "[PLAN]\n(attack a)\n(overcome a c)\n(attack b)\n(overcome b a)\n[PLAN END]\n"
        )
        self.system_prompt = (
            "Eres un planificador STRIPS. Da tu respuesta final SOLO como una lista de acciones "
            "en formato (accion arg1 arg2), usando los nombres de accion EN CODIGO del ejemplo "
            "(no el texto en ingles del enunciado), entre [PLAN] y [PLAN END]."
        )

    def solve(self, scenario_context: str, llm_engine_func) -> list:
        domain, init_state, goal_state, objects = parse_problem(scenario_context)
        actions = ACTIONS_FN[domain](objects)

        init_txt = ", ".join(str(f) for f in sorted(init_state))
        goal_txt = ", ".join(str(f) for f in sorted(goal_state))
        prompt = f"{domain}. Inicial: {init_txt}. Meta: {goal_txt}. Plan:"

        try:
            respuesta = llm_engine_func(
                prompt=prompt, system=None,
                temperature=0.0, do_sample=False, max_new_tokens=4,
            )
            plan_llm = self._parse_llm_plan(respuesta)
            if plan_llm and self._validar_plan(plan_llm, domain, init_state, goal_state):
                return plan_llm
        except Exception:
            pass

        plan_bfs = bfs_plan(init_state, goal_state, actions)
        return format_plan(domain, plan_bfs) if plan_bfs else []

    def _parse_llm_plan(self, texto):
        m = re.search(r'\[PLAN\](.*?)(\[PLAN END\]|$)', texto, re.S)
        bloque = m.group(1) if m else texto
        acciones = re.findall(r'\(([a-zA-Z_]+(?:\s+\w+)*)\)', bloque)
        return [f"({a.strip()})" for a in acciones] if acciones else None

    def _validar_plan(self, plan_texto, domain, init_state, goal_state):
        state = set(init_state)
        inv_map = {v: k for k, v in CODE_MAP[domain].items()}
        for accion_str in plan_texto:
            parts = accion_str.strip('()').split()
            if not parts:
                return False
            code, args = parts[0], tuple(parts[1:])
            name = inv_map.get(code)
            if name is None:
                return False
            match = next((a for a in ACTIONS_FN[domain](args) if a[0] == name and a[1] == args), None)
            if match is None or not match[2].issubset(state):
                return False
            state = (state - match[4]) | match[3]
        return goal_state.issubset(state)
