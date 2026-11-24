import { useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { Link, useSearchParams } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { TextField } from "@/components/ui/input";
import { forgotPassword, resetPassword, resetPasswordWithToken } from "@/features/auth/api";
import { AuthHeading, FormError } from "@/layouts/AuthLayout";
import { errorMessage } from "@/utils/errors";

function BackToLogin() {
  const { t } = useTranslation();
  return (
    <p className="mt-5 text-center text-sm">
      <Link to="/login" className="font-medium text-secondary hover:underline">
        {t("auth.backToLogin")}
      </Link>
    </p>
  );
}

function Notice({ children }: { children: string }) {
  return (
    <p role="status" className="rounded-md border border-success/30 bg-success/10 px-3 py-2 text-sm text-success">
      {children}
    </p>
  );
}

function PasswordResetFlow({ inviteToken }: { inviteToken?: string | null }) {
  const { t } = useTranslation();
  const [email, setEmail] = useState("");
  const [code, setCode] = useState("");
  const [password, setPassword] = useState("");
  const [sent, setSent] = useState(false);
  const [done, setDone] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function sendCode(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setBusy(true);
    try {
      await forgotPassword(email.trim());
      setSent(true);
    } catch (err) {
      setError(errorMessage(err, t));
    } finally {
      setBusy(false);
    }
  }

  async function submitReset(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    if (!inviteToken && !/^\d{6}$/.test(code)) {
      setError(t("auth.codeInvalid"));
      return;
    }
    if (password.length < 10) {
      setError(t("validation.passwordMin"));
      return;
    }
    setBusy(true);
    try {
      if (inviteToken) await resetPasswordWithToken(inviteToken, password);
      else await resetPassword(email.trim(), code, password);
      setDone(true);
    } catch (err) {
      setError(errorMessage(err, t));
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <AuthHeading
        title={t(done || inviteToken ? "auth.resetTitle" : "auth.forgotTitle")}
        subtitle={t(done || inviteToken ? "auth.resetSubtitle" : sent ? "auth.codeSubtitle" : "auth.forgotSubtitle")}
      />
      {done ? (
        <Notice>{t("auth.resetDone")}</Notice>
      ) : inviteToken ? (
        <form onSubmit={submitReset} className="space-y-4">
          <FormError message={error} />
          <TextField
            label={t("auth.newPassword")}
            type="password"
            dir="ltr"
            autoComplete="new-password"
            required
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            hint={t("auth.passwordHint")}
          />
          <Button type="submit" className="w-full" disabled={busy || password.length < 10}>
            {busy ? t("auth.resetting") : t("auth.savePassword")}
          </Button>
        </form>
      ) : !sent ? (
        <form onSubmit={sendCode} className="space-y-4">
          <FormError message={error} />
          <TextField
            label={t("auth.email")}
            type="email"
            dir="ltr"
            autoComplete="email"
            required
            value={email}
            onChange={(event) => setEmail(event.target.value)}
          />
          <Button type="submit" className="w-full" disabled={busy || !email.trim()}>
            {busy ? t("auth.sendingCode") : t("auth.sendCode")}
          </Button>
        </form>
      ) : (
        <form onSubmit={submitReset} className="space-y-4">
          <Notice>{t("auth.codeSent")}</Notice>
          <FormError message={error} />
          <TextField
            label={t("auth.email")}
            type="email"
            dir="ltr"
            autoComplete="email"
            required
            value={email}
            onChange={(event) => setEmail(event.target.value)}
          />
          <TextField
            label={t("auth.otpCode")}
            type="text"
            dir="ltr"
            inputMode="numeric"
            autoComplete="one-time-code"
            maxLength={6}
            required
            value={code}
            onChange={(event) => setCode(event.target.value.replace(/\D/g, "").slice(0, 6))}
          />
          <TextField
            label={t("auth.newPassword")}
            type="password"
            dir="ltr"
            autoComplete="new-password"
            required
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            hint={t("auth.passwordHint")}
          />
          <Button type="submit" className="w-full" disabled={busy || code.length !== 6 || password.length < 10}>
            {busy ? t("auth.resetting") : t("auth.savePassword")}
          </Button>
          <button
            type="button"
            className="w-full text-sm font-medium text-secondary hover:underline"
            disabled={busy}
            onClick={() => { setSent(false); setCode(""); setPassword(""); setError(null); }}
          >
            {t("auth.changeEmail")}
          </button>
        </form>
      )}
      <BackToLogin />
    </>
  );
}

export function ForgotPasswordPage() {
  return <PasswordResetFlow />;
}

export function ResetPasswordPage() {
  const [searchParams] = useSearchParams();
  return <PasswordResetFlow inviteToken={searchParams.get("token")} />;
}
