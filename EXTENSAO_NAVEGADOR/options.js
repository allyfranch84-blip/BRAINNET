const token = document.getElementById("token");
const status = document.getElementById("status");
chrome.storage.local.get("bridgeToken").then(({bridgeToken}) => {
  status.textContent = bridgeToken ? "Token configurado. Conexão ainda não verificada." : "Sem token configurado.";
});
document.getElementById("save").addEventListener("click", async () => {
  const value = token.value.trim();
  if (!/^[0-9a-f]{64}$/.test(value)) { status.textContent = "Token inválido."; return; }
  try {
    await chrome.storage.local.set({bridgeToken:value});
    token.value="";
    status.textContent="Token salvo. Verifique a conexão no kernel.";
  } catch (_) { status.textContent="Falha ao salvar token."; }
});
document.getElementById("clear").addEventListener("click", async () => {
  try {
    await chrome.storage.local.remove("bridgeToken");
    token.value="";
    status.textContent="Token removido.";
  } catch (_) { status.textContent="Falha ao remover token."; }
});
