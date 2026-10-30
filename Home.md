---
cssclasses: [orbitus-home]
---

```dataviewjs
const h = new Date().getHours();
const saud = h < 12 ? "Bom dia" : h < 18 ? "Boa tarde" : "Boa noite";
const hoje = new Date().toLocaleDateString("pt-BR", {weekday:"long", day:"numeric", month:"long"});
const sis = dv.pages('"01_Federacao"').where(p => p.tipo === "federacao").array();
const ord = {"🔴":0,"🟡":1,"⚪":2,"🟢":3};
sis.sort((a,b) => ord[a.saude]-ord[b.saude]);
const vermelhos = sis.filter(s => s.saude === "🔴").length;
const esc = t => String(t ?? "").replace(/[&<>]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;"}[c]));

const hero = dv.el("div", "", {cls: "orb-hero"});
hero.innerHTML = `
  <div class="orb-aurora"></div>
  <div class="orb-hero-txt">
    <div class="orb-kicker">ORBITUS · ${esc(hoje)}</div>
    <h1>${saud}, Marcio.</h1>
    <p>${vermelhos === 0 ? "Todos os sistemas em órbita." : vermelhos === 1 ? "1 sistema pede atenção." : vermelhos + " sistemas pedem atenção."}</p>
  </div>`;

const esp = sis.filter(s => s.esperando);
if (esp.length) {
  const box = dv.el("div", "", {cls: "orb-card orb-wait"});
  box.innerHTML = `<div class="orb-label">Esperando de você</div>` +
    esp.map(s => `<div class="orb-wait-item"><span>${s.icone}</span><div><b>${esc(s.nome)}</b><br>${esc(s.esperando)}</div></div>`).join("");
}

const grid = dv.el("div", "", {cls: "orb-grid"});
grid.innerHTML = sis.map((s, i) => `
  <a class="orb-card orb-sys internal-link" data-href="${s.file.path}" href="${s.file.path}" style="--i:${i}">
    <div class="orb-sys-top"><span class="orb-dot s${ord[s.saude]}"></span><span class="orb-sys-name">${s.icone} ${esc(s.nome)}</span></div>
    <div class="orb-sys-meta">Status de ${esc(s.data_base || "—")} · ${s.idade >= 0 ? s.idade + "d" : "?"}</div>
    ${s.motivo ? `<div class="orb-sys-warn">${esc(s.motivo)}</div>` : ""}
    ${(s.falhas || []).map(f => `<div class="orb-sys-fail">✕ ${esc(f)}</div>`).join("")}
    <div class="orb-sys-next">${esc(s.proxima || "")}</div>
  </a>`).join("");
```

## ◎ Hoje

```tasks
not done
(due before tomorrow) OR (priority is highest)
path includes 10_Tarefas
sort by priority
sort by due
hide edit button
short mode
```

## → Próximos 7 dias

```tasks
not done
due after today
due before in 8 days
path includes 10_Tarefas
sort by due
group by due
short mode
```

## ✉ E-mails que pedem resposta

![[20_Email/Caixa#Pedem resposta]]

---
[[10_Tarefas/Tarefas|Todas as tarefas]] · [[90_Ideias/Ideias|Ideias]] · [[CLAUDE|Como o Orbitus funciona]]
