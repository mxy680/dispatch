import * as vscode from "vscode";

type ContextPayload = {
  projectId: string;
  filePath: string;
  selection: string;
  diagnostics: string;
};

function collectDiagnosticsForUri(uri: vscode.Uri): string {
  const diagnostics = vscode.languages.getDiagnostics(uri);
  return diagnostics
    .map((d) => {
      const sev =
        d.severity === vscode.DiagnosticSeverity.Error
          ? "error"
          : d.severity === vscode.DiagnosticSeverity.Warning
          ? "warning"
          : "info";
      return `${sev}: ${d.message}`;
    })
    .join("\n");
}

export function activate(context: vscode.ExtensionContext) {
  const disposable = vscode.commands.registerCommand("dispatch.sendContext", async () => {
    const cfg = vscode.workspace.getConfiguration("dispatch");
    const projectId = String(cfg.get<string>("projectId") || "");
    const bridge = String(cfg.get<string>("localBridgeUrl") || "http://127.0.0.1:43111");
    if (!projectId) {
      vscode.window.showErrorMessage("Set dispatch.projectId in settings first.");
      return;
    }

    const editor = vscode.window.activeTextEditor;
    if (!editor) {
      vscode.window.showErrorMessage("No active editor.");
      return;
    }

    const filePath = editor.document.uri.fsPath;
    const selection = editor.document.getText(editor.selection);
    const diagnostics = collectDiagnosticsForUri(editor.document.uri);

    const payload: ContextPayload = {
      projectId,
      filePath,
      selection,
      diagnostics,
    };

    try {
      const res = await fetch(`${bridge}/context`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!res.ok) {
        throw new Error(await res.text());
      }
      vscode.window.showInformationMessage("Dispatch context sent to companion.");
    } catch (err) {
      vscode.window.showErrorMessage(`Dispatch companion unreachable: ${String(err)}`);
    }
  });

  context.subscriptions.push(disposable);
}

export function deactivate() {}

