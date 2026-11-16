import "./global.css";

import AppProvider from "@/app/provider";
import AppRouter from "@/app/router";
import { LicenseGate } from "@/features/license/LicenseGate";

export default function App() {
  return (
    <AppProvider>
      <LicenseGate>
        <AppRouter />
      </LicenseGate>
    </AppProvider>
  );
}
