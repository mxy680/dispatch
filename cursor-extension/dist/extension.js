"use strict";
var __createBinding = (this && this.__createBinding) || (Object.create ? (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    var desc = Object.getOwnPropertyDescriptor(m, k);
    if (!desc || ("get" in desc ? !m.__esModule : desc.writable || desc.configurable)) {
      desc = { enumerable: true, get: function() { return m[k]; } };
    }
    Object.defineProperty(o, k2, desc);
}) : (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    o[k2] = m[k];
}));
var __setModuleDefault = (this && this.__setModuleDefault) || (Object.create ? (function(o, v) {
    Object.defineProperty(o, "default", { enumerable: true, value: v });
}) : function(o, v) {
    o["default"] = v;
});
var __importStar = (this && this.__importStar) || (function () {
    var ownKeys = function(o) {
        ownKeys = Object.getOwnPropertyNames || function (o) {
            var ar = [];
            for (var k in o) if (Object.prototype.hasOwnProperty.call(o, k)) ar[ar.length] = k;
            return ar;
        };
        return ownKeys(o);
    };
    return function (mod) {
        if (mod && mod.__esModule) return mod;
        var result = {};
        if (mod != null) for (var k = ownKeys(mod), i = 0; i < k.length; i++) if (k[i] !== "default") __createBinding(result, mod, k[i]);
        __setModuleDefault(result, mod);
        return result;
    };
})();
Object.defineProperty(exports, "__esModule", { value: true });
exports.activate = activate;
exports.deactivate = deactivate;
const vscode = __importStar(require("vscode"));
function collectDiagnosticsForUri(uri) {
    const diagnostics = vscode.languages.getDiagnostics(uri);
    return diagnostics
        .map((d) => {
        const sev = d.severity === vscode.DiagnosticSeverity.Error
            ? "error"
            : d.severity === vscode.DiagnosticSeverity.Warning
                ? "warning"
                : "info";
        return `${sev}: ${d.message}`;
    })
        .join("\n");
}
function activate(context) {
    const disposable = vscode.commands.registerCommand("dispatch.sendContext", async () => {
        const cfg = vscode.workspace.getConfiguration("dispatch");
        const projectId = String(cfg.get("projectId") || "");
        const bridge = String(cfg.get("localBridgeUrl") || "http://127.0.0.1:43111");
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
        const payload = {
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
        }
        catch (err) {
            vscode.window.showErrorMessage(`Dispatch companion unreachable: ${String(err)}`);
        }
    });
    context.subscriptions.push(disposable);
}
function deactivate() { }
