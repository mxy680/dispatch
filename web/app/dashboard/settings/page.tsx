import { SettingsAgentsPanel } from "@/components/settings-agents-panel";
import { SettingsDangerZone } from "@/components/settings-danger-zone";

export default function SettingsPage() {
  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold tracking-tight">Settings</h1>

      <section className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="space-y-6">
          <SettingsAgentsPanel />
        </div>
        <div className="space-y-6">
          <SettingsDangerZone />
        </div>
      </section>
    </div>
  );
}
