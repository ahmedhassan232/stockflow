import { Download, FileText } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import type { Params } from "@/features/data/api";
import { api } from "@/services/api";

/** Downloads a CSV or PDF through the authenticated API client (a plain link would not carry
 *  the access token, which lives in memory only). */
export function ExportButton({ path, params, filename, kind = "csv" }: { path: string; params?: Params; filename: string; kind?: "csv" | "pdf" }) {
  const { t } = useTranslation();
  const [state, setState] = useState<"idle" | "busy" | "failed">("idle");
  const download = async () => {
    setState("busy");
    try {
      const clean = Object.fromEntries(Object.entries(params ?? {}).filter(([, v]) => v !== undefined && v !== null && v !== ""));
      const res = await api.get<Blob>(path, { params: clean, responseType: "blob" });
      const url = URL.createObjectURL(res.data);
      const link = document.createElement("a");
      link.href = url;
      link.download = filename;
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
      setState("idle");
    } catch {
      setState("failed");
    }
  };
  return (
    <Button variant="outline" onClick={() => void download()} disabled={state === "busy"} className="print:hidden">
      {kind === "pdf" ? <FileText /> : <Download />}
      {state === "failed" ? t("export.failed") : state === "busy" ? t("common.loading") : t(kind === "pdf" ? "export.pdf" : "export.csv")}
    </Button>
  );
}
