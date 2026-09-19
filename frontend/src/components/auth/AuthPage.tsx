import { useMemo, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  AlertCircle,
  ArrowRight,
  BrainCircuit,
  Check,
  ChevronDown,
  Eye,
  EyeOff,
  FileText,
  HeartPulse,
  Loader2,
  Lock,
  Mail,
  ShieldCheck,
  Sparkles,
  Stethoscope,
  User,
} from "lucide-react";
import { FaReact, FaPython } from "react-icons/fa";
import { SiFastapi, SiPostgresql } from "react-icons/si";

type AuthMode = "login" | "register";

interface AuthPageProps {
  mode: AuthMode;
  error: string;
  onModeChange: (mode: AuthMode) => void;
  onLogin: (email: string, password: string) => Promise<void>;
  onRegister: (fullName: string, email: string, password: string) => Promise<void>;
}

interface FieldErrorMap {
  fullName?: string;
  email?: string;
  password?: string;
  confirmPassword?: string;
  terms?: string;
  disclaimer?: string;
}

const roles = [
  "Doctor",
  "Medical Student",
  "Researcher",
  "Healthcare Professional",
  "Administrator",
  "Other",
];

const heroFeatures = [
  "Secure Authentication",
  "AI Medical Assistant",
  "PDF Medical Report Analysis",
  "Retrieval-Augmented Generation (RAG)",
  "Local Llama 3 AI",
  "FAISS Semantic Search",
  "Evidence-based Responses",
  "Privacy Focused",
];

function isValidEmail(value: string) {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value.trim());
}

function passwordScore(password: string) {
  let score = 0;
  if (password.length >= 8) score += 1;
  if (/[A-Z]/.test(password)) score += 1;
  if (/[0-9]/.test(password)) score += 1;
  if (/[^A-Za-z0-9]/.test(password)) score += 1;
  return score;
}

function passwordLabel(score: number) {
  if (score <= 1) return "Weak";
  if (score === 2) return "Fair";
  if (score === 3) return "Good";
  return "Strong";
}

function passwordBarColor(score: number) {
  if (score <= 1) return "bg-rose-500";
  if (score === 2) return "bg-amber-500";
  if (score === 3) return "bg-sky-500";
  return "bg-emerald-500";
}

function TextField({
  id,
  label,
  value,
  onChange,
  type = "text",
  icon,
  placeholder,
  error,
  autoComplete,
  rightSlot,
}: {
  id: string;
  label: string;
  value: string;
  onChange: (value: string) => void;
  type?: string;
  icon: React.ReactNode;
  placeholder: string;
  error?: string;
  autoComplete?: string;
  rightSlot?: React.ReactNode;
}) {
  return (
    <label htmlFor={id} className="block">
      <span className="mb-2 block text-sm font-semibold text-slate-700">{label}</span>
      <div
        className={`flex min-h-12 items-center rounded-2xl border bg-white/85 px-4 shadow-sm transition focus-within:border-blue-500 focus-within:ring-4 focus-within:ring-blue-100 ${
          error ? "border-rose-300" : "border-slate-200"
        }`}
      >
        <span className="mr-3 text-slate-400">{icon}</span>
        <input
          id={id}
          type={type}
          value={value}
          onChange={(event) => onChange(event.target.value)}
          placeholder={placeholder}
          autoComplete={autoComplete}
          aria-invalid={!!error}
          aria-describedby={error ? `${id}-error` : undefined}
          className="min-w-0 flex-1 bg-transparent py-3 text-sm text-slate-900 outline-none placeholder:text-slate-400"
        />
        {rightSlot}
      </div>
      <AnimatePresence>
        {error && (
          <motion.p
            id={`${id}-error`}
            initial={{ opacity: 0, y: -4 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -4 }}
            className="mt-2 flex items-center gap-1.5 text-xs font-medium text-rose-600"
          >
            <AlertCircle className="h-3.5 w-3.5" />
            {error}
          </motion.p>
        )}
      </AnimatePresence>
    </label>
  );
}

function CheckboxField({
  id,
  checked,
  onChange,
  children,
  error,
}: {
  id: string;
  checked: boolean;
  onChange: (checked: boolean) => void;
  children: React.ReactNode;
  error?: string;
}) {
  return (
    <div>
      <label htmlFor={id} className="flex cursor-pointer items-start gap-3 rounded-2xl border border-slate-200 bg-white/70 p-3 text-sm text-slate-600 transition hover:border-blue-200 hover:bg-blue-50/40">
        <input
          id={id}
          type="checkbox"
          checked={checked}
          onChange={(event) => onChange(event.target.checked)}
          className="mt-1 h-4 w-4 rounded border-slate-300 text-blue-600 focus:ring-blue-500"
        />
        <span>{children}</span>
      </label>
      {error && <p className="mt-2 text-xs font-medium text-rose-600">{error}</p>}
    </div>
  );
}

function PasswordStrength({ password }: { password: string }) {
  const score = passwordScore(password);
  const active = password.length > 0;

  return (
    <div className="mt-3" aria-live="polite">
      <div className="mb-2 flex items-center justify-between text-xs">
        <span className="font-medium text-slate-500">Password strength</span>
        <span className={`font-semibold ${active && score >= 3 ? "text-emerald-600" : "text-slate-500"}`}>
          {active ? passwordLabel(score) : "Enter password"}
        </span>
      </div>
      <div className="grid grid-cols-4 gap-2">
        {[1, 2, 3, 4].map((step) => (
          <div key={step} className="h-2 rounded-full bg-slate-200">
            <motion.div
              initial={false}
              animate={{ width: active && score >= step ? "100%" : "0%" }}
              className={`h-full rounded-full ${passwordBarColor(score)}`}
            />
          </div>
        ))}
      </div>
    </div>
  );
}

function Notification({ type, message }: { type: "error" | "success"; message: string }) {
  const isError = type === "error";
  return (
    <motion.div
      initial={{ opacity: 0, y: -8 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -8 }}
      role={isError ? "alert" : "status"}
      className={`flex items-start gap-3 rounded-2xl border px-4 py-3 text-sm shadow-sm ${
        isError
          ? "border-rose-200 bg-rose-50 text-rose-700"
          : "border-emerald-200 bg-emerald-50 text-emerald-700"
      }`}
    >
      {isError ? <AlertCircle className="mt-0.5 h-4 w-4" /> : <Check className="mt-0.5 h-4 w-4" />}
      <span>{message}</span>
    </motion.div>
  );
}

function AuthHero() {
  return (
    <aside className="relative hidden min-h-full overflow-hidden bg-gradient-to-br from-blue-950 via-blue-900 to-slate-900 p-8 text-white lg:flex lg:flex-col lg:justify-between">
      <div className="absolute inset-0 opacity-20 [background-image:radial-gradient(circle_at_25%_15%,#93c5fd_0,transparent_28%),radial-gradient(circle_at_80%_25%,#22d3ee_0,transparent_22%)]" />
      <div className="relative">
        <div className="mb-8 inline-flex items-center gap-2 rounded-full border border-white/15 bg-white/10 px-4 py-2 text-sm text-blue-50 shadow-lg backdrop-blur">
          <ShieldCheck className="h-4 w-4" />
          Healthcare-grade AI workspace
        </div>

        <motion.div
          initial={{ opacity: 0, y: 18 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.55 }}
          className="rounded-[2rem] border border-white/15 bg-white/10 p-7 shadow-2xl backdrop-blur-xl"
        >
          <div className="mb-6 grid h-64 place-items-center rounded-[1.5rem] bg-white/95 p-6 shadow-inner">
            <div className="relative h-full w-full">
              <motion.div
                animate={{ y: [0, -8, 0] }}
                transition={{ duration: 4, repeat: Infinity, ease: "easeInOut" }}
                className="absolute left-1/2 top-4 flex h-24 w-24 -translate-x-1/2 items-center justify-center rounded-full bg-blue-100 text-blue-700 shadow-lg"
              >
                <BrainCircuit className="h-12 w-12" />
              </motion.div>
              <div className="absolute bottom-4 left-1/2 h-28 w-52 -translate-x-1/2 rounded-3xl bg-slate-100 shadow-xl">
                <div className="mx-auto mt-5 h-12 w-12 rounded-full bg-sky-100 text-sky-700 grid place-items-center">
                  <Stethoscope className="h-7 w-7" />
                </div>
                <div className="mx-auto mt-4 h-2 w-32 rounded-full bg-slate-300" />
                <div className="mx-auto mt-2 h-2 w-24 rounded-full bg-slate-200" />
              </div>
              <div className="absolute left-2 top-20 rounded-2xl bg-emerald-50 p-3 text-emerald-700 shadow-lg">
                <HeartPulse className="h-7 w-7" />
              </div>
              <div className="absolute right-3 top-28 rounded-2xl bg-blue-50 p-3 text-blue-700 shadow-lg">
                <FileText className="h-7 w-7" />
              </div>
            </div>
          </div>

          <h2 className="text-3xl font-bold leading-tight">AI-Powered Clinical Knowledge Assistant</h2>
          <p className="mt-4 text-sm leading-7 text-blue-50/85">
            Upload trusted medical reports. Ask evidence-based medical questions. Receive AI-generated answers with source citations. Built for healthcare professionals, students, and researchers.
          </p>
        </motion.div>

        <div className="mt-6 grid grid-cols-2 gap-3">
          {heroFeatures.map((feature, index) => (
            <motion.div
              key={feature}
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.06 * index }}
              className="flex items-center gap-2 rounded-2xl border border-white/10 bg-white/10 px-3 py-3 text-sm text-blue-50 backdrop-blur"
            >
              <Check className="h-4 w-4 shrink-0 text-emerald-300" />
              {feature}
            </motion.div>
          ))}
        </div>
      </div>

      <div className="relative mt-8 rounded-2xl border border-white/15 bg-white/10 p-4 text-xs leading-6 text-blue-50/80 backdrop-blur">
        MediRAG AI provides information retrieved from uploaded medical documents. It is intended for educational and clinical reference purposes only and should not replace professional medical judgment.
      </div>
    </aside>
  );
}

export default function AuthPage({ mode, error, onModeChange, onLogin, onRegister }: AuthPageProps) {
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [organization, setOrganization] = useState("");
  const [role, setRole] = useState(roles[0]);
  const [rememberMe, setRememberMe] = useState(false);
  const [acceptedTerms, setAcceptedTerms] = useState(false);
  const [acceptedDisclaimer, setAcceptedDisclaimer] = useState(false);
  const [showPassword, setShowPassword] = useState(false);
  const [showConfirmPassword, setShowConfirmPassword] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [fieldErrors, setFieldErrors] = useState<FieldErrorMap>({});
  const [success, setSuccess] = useState("");

  const isRegister = mode === "register";
  const currentPasswordScore = useMemo(() => passwordScore(password), [password]);

  const validate = () => {
    const nextErrors: FieldErrorMap = {};

    if (isRegister && !fullName.trim()) nextErrors.fullName = "Please enter your full name.";
    if (!email.trim()) nextErrors.email = "Please enter your email address.";
    else if (!isValidEmail(email)) nextErrors.email = "Enter a valid email address.";
    if (!password) nextErrors.password = "Please enter your password.";
    else if (isRegister && password.length < 8) nextErrors.password = "Use at least 8 characters.";
    if (isRegister && confirmPassword !== password) nextErrors.confirmPassword = "Passwords do not match.";
    if (isRegister && !acceptedTerms) nextErrors.terms = "You must agree to the Terms of Service.";
    if (isRegister && !acceptedDisclaimer) nextErrors.disclaimer = "Please acknowledge the clinical support disclaimer.";

    setFieldErrors(nextErrors);
    return Object.keys(nextErrors).length === 0;
  };

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    setSuccess("");

    if (!validate()) return;

    setIsLoading(true);
    try {
      if (isRegister) {
        await onRegister(fullName.trim(), email.trim(), password);
        setSuccess("Account created successfully. Redirecting to your workspace...");
      } else {
        await onLogin(email.trim(), password);
        setSuccess("Signed in successfully. Loading your workspace...");
      }
    } finally {
      setIsLoading(false);
    }
  };

  const switchMode = (nextMode: AuthMode) => {
    setFieldErrors({});
    setSuccess("");
    setShowPassword(false);
    setShowConfirmPassword(false);
    onModeChange(nextMode);
  };

  return (
    <main className="min-h-screen bg-slate-50 text-slate-900">
      <div className="grid min-h-screen lg:grid-cols-[minmax(0,0.96fr)_minmax(440px,0.8fr)]">
        <section className="flex min-h-screen flex-col justify-between px-4 py-6 sm:px-8 lg:px-12">
          <div className="mx-auto flex w-full max-w-2xl items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="grid h-11 w-11 place-items-center rounded-2xl bg-blue-600 text-white shadow-lg shadow-blue-600/25">
                <Sparkles className="h-5 w-5" />
              </div>
              <div>
                <p className="text-lg font-bold text-blue-950">MediRAG AI</p>
                <p className="text-xs font-medium text-slate-500">Clinical reference workspace</p>
              </div>
            </div>
            <div className="hidden items-center gap-2 rounded-full border border-slate-200 bg-white px-3 py-2 text-xs font-semibold text-slate-600 shadow-sm sm:flex">
              <Lock className="h-3.5 w-3.5 text-blue-600" />
              Secure session
            </div>
          </div>

          <motion.div
            key={mode}
            initial={{ opacity: 0, x: isRegister ? 18 : -18 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ duration: 0.35 }}
            className="mx-auto my-8 w-full max-w-2xl"
          >
            <div className="rounded-[2rem] border border-white/80 bg-white/85 p-5 shadow-2xl shadow-blue-950/10 backdrop-blur sm:p-8">
              <div className="mb-8">
                <p className="mb-3 inline-flex items-center gap-2 rounded-full bg-blue-50 px-3 py-1 text-xs font-bold uppercase tracking-wide text-blue-700">
                  <ShieldCheck className="h-3.5 w-3.5" />
                  {isRegister ? "New secure account" : "Secure access"}
                </p>
                <h1 className="text-3xl font-bold tracking-tight text-blue-950 sm:text-4xl">
                  {isRegister ? "Create Your MediRAG AI Account" : "Welcome Back"}
                </h1>
                <p className="mt-3 max-w-xl text-sm leading-6 text-slate-600 sm:text-base">
                  {isRegister
                    ? "Securely access AI-powered medical document analysis and evidence-based clinical assistance."
                    : "Sign in securely to continue using MediRAG AI."}
                </p>
              </div>

              <div className="mb-6 grid grid-cols-2 rounded-2xl bg-slate-100 p-1">
                <button
                  type="button"
                  onClick={() => switchMode("login")}
                  className={`rounded-xl px-4 py-3 text-sm font-semibold transition ${
                    !isRegister ? "bg-white text-blue-700 shadow-sm" : "text-slate-500 hover:text-slate-800"
                  }`}
                >
                  Sign In
                </button>
                <button
                  type="button"
                  onClick={() => switchMode("register")}
                  className={`rounded-xl px-4 py-3 text-sm font-semibold transition ${
                    isRegister ? "bg-white text-blue-700 shadow-sm" : "text-slate-500 hover:text-slate-800"
                  }`}
                >
                  Create Account
                </button>
              </div>

              <AnimatePresence mode="wait">
                {(error || success) && (
                  <div className="mb-6">
                    {error && <Notification type="error" message={error} />}
                    {!error && success && <Notification type="success" message={success} />}
                  </div>
                )}
              </AnimatePresence>

              <form onSubmit={handleSubmit} className="space-y-5" noValidate>
                {isRegister && (
                  <TextField
                    id="fullName"
                    label="Full Name"
                    value={fullName}
                    onChange={setFullName}
                    placeholder="Dr. Arun Kumar"
                    icon={<User className="h-4 w-4" />}
                    error={fieldErrors.fullName}
                    autoComplete="name"
                  />
                )}

                <TextField
                  id="email"
                  label={isRegister ? "Email Address" : "Email"}
                  value={email}
                  onChange={setEmail}
                  type="email"
                  placeholder="name@hospital.org"
                  icon={<Mail className="h-4 w-4" />}
                  error={fieldErrors.email}
                  autoComplete="email"
                />

                {isRegister && (
                  <div className="grid gap-5 sm:grid-cols-2">
                    <TextField
                      id="organization"
                      label="Organization / Hospital"
                      value={organization}
                      onChange={setOrganization}
                      placeholder="General Hospital"
                      icon={<Stethoscope className="h-4 w-4" />}
                      autoComplete="organization"
                    />
                    <label htmlFor="role" className="block">
                      <span className="mb-2 block text-sm font-semibold text-slate-700">Role</span>
                      <div className="relative">
                        <select
                          id="role"
                          value={role}
                          onChange={(event) => setRole(event.target.value)}
                          className="min-h-12 w-full appearance-none rounded-2xl border border-slate-200 bg-white/85 px-4 py-3 pr-10 text-sm font-medium text-slate-700 shadow-sm outline-none transition focus:border-blue-500 focus:ring-4 focus:ring-blue-100"
                        >
                          {roles.map((roleOption) => (
                            <option key={roleOption}>{roleOption}</option>
                          ))}
                        </select>
                        <ChevronDown className="pointer-events-none absolute right-4 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
                      </div>
                    </label>
                  </div>
                )}

                <TextField
                  id="password"
                  label="Password"
                  value={password}
                  onChange={setPassword}
                  type={showPassword ? "text" : "password"}
                  placeholder={isRegister ? "Create a secure password" : "Enter your password"}
                  icon={<Lock className="h-4 w-4" />}
                  error={fieldErrors.password}
                  autoComplete={isRegister ? "new-password" : "current-password"}
                  rightSlot={
                    <button
                      type="button"
                      onClick={() => setShowPassword((value) => !value)}
                      className="rounded-full p-1.5 text-slate-400 transition hover:bg-slate-100 hover:text-blue-700"
                      aria-label={showPassword ? "Hide password" : "Show password"}
                    >
                      {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                    </button>
                  }
                />

                {isRegister && <PasswordStrength password={password} />}

                {isRegister && (
                  <TextField
                    id="confirmPassword"
                    label="Confirm Password"
                    value={confirmPassword}
                    onChange={setConfirmPassword}
                    type={showConfirmPassword ? "text" : "password"}
                    placeholder="Re-enter your password"
                    icon={<Lock className="h-4 w-4" />}
                    error={fieldErrors.confirmPassword}
                    autoComplete="new-password"
                    rightSlot={
                      <button
                        type="button"
                        onClick={() => setShowConfirmPassword((value) => !value)}
                        className="rounded-full p-1.5 text-slate-400 transition hover:bg-slate-100 hover:text-blue-700"
                        aria-label={showConfirmPassword ? "Hide confirm password" : "Show confirm password"}
                      >
                        {showConfirmPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                      </button>
                    }
                  />
                )}

                {isRegister ? (
                  <div className="rounded-3xl border border-blue-100 bg-blue-50/70 p-5">
                    <div className="mb-4 flex items-center gap-3">
                      <div className="grid h-10 w-10 place-items-center rounded-2xl bg-white text-blue-700 shadow-sm">
                        <Lock className="h-5 w-5" />
                      </div>
                      <div>
                        <h2 className="font-bold text-blue-950">Secure Authentication</h2>
                        <p className="text-xs text-slate-600">Medical documents remain private.</p>
                      </div>
                    </div>
                    <div className="grid gap-2 text-sm text-slate-700 sm:grid-cols-3">
                      <span className="flex items-center gap-2"><Check className="h-4 w-4 text-emerald-600" />Passwords are encrypted.</span>
                      <span className="flex items-center gap-2"><Check className="h-4 w-4 text-emerald-600" />Files are never shared.</span>
                      <span className="flex items-center gap-2"><Check className="h-4 w-4 text-emerald-600" />Private workspace.</span>
                    </div>
                  </div>
                ) : (
                  <div className="flex flex-wrap items-center justify-between gap-3 text-sm">
                    <label className="flex cursor-pointer items-center gap-2 text-slate-600">
                      <input
                        type="checkbox"
                        checked={rememberMe}
                        onChange={(event) => setRememberMe(event.target.checked)}
                        className="h-4 w-4 rounded border-slate-300 text-blue-600 focus:ring-blue-500"
                      />
                      Remember Me
                    </label>
                    <button type="button" className="font-semibold text-blue-700 transition hover:text-blue-900">
                      Forgot Password?
                    </button>
                  </div>
                )}

                {isRegister && (
                  <div className="space-y-3">
                    <CheckboxField id="terms" checked={acceptedTerms} onChange={setAcceptedTerms} error={fieldErrors.terms}>
                      I agree to the Terms of Service
                    </CheckboxField>
                    <CheckboxField id="clinicalDisclaimer" checked={acceptedDisclaimer} onChange={setAcceptedDisclaimer} error={fieldErrors.disclaimer}>
                      I understand that MediRAG AI is an AI-powered clinical support system and does not replace professional medical advice.
                    </CheckboxField>
                  </div>
                )}

                <button
                  type="submit"
                  disabled={isLoading || (isRegister && currentPasswordScore < 1)}
                  className="group flex min-h-12 w-full items-center justify-center gap-2 rounded-2xl bg-blue-600 px-5 py-3 text-sm font-bold text-white shadow-xl shadow-blue-600/25 transition hover:-translate-y-0.5 hover:bg-blue-700 focus:outline-none focus:ring-4 focus:ring-blue-200 disabled:cursor-not-allowed disabled:opacity-70 disabled:hover:translate-y-0"
                >
                  {isLoading ? (
                    <Loader2 className="h-5 w-5 animate-spin" />
                  ) : (
                    <>
                      {isRegister ? "Create Account" : "Sign In"}
                      <ArrowRight className="h-4 w-4 transition group-hover:translate-x-1" />
                    </>
                  )}
                </button>
              </form>

              <p className="mt-7 text-center text-sm text-slate-600">
                {isRegister ? "Already have an account?" : "Need a new workspace?"}{" "}
                <button
                  type="button"
                  onClick={() => switchMode(isRegister ? "login" : "register")}
                  className="font-bold text-blue-700 transition hover:text-blue-900"
                >
                  {isRegister ? "Sign In" : "Create Account"}
                </button>
              </p>
            </div>
          </motion.div>

          <footer className="mx-auto w-full max-w-2xl text-center text-xs leading-6 text-slate-500">
            <div className="mb-2 flex flex-wrap items-center justify-center gap-2 text-slate-400">
              <FaReact className="h-4 w-4" />
              <SiFastapi className="h-4 w-4" />
              <SiPostgresql className="h-4 w-4" />
              <FaPython className="h-4 w-4" />
            </div>
            <p>© 2026 MediRAG AI · Version 1.0</p>
            <p>Powered by React • FastAPI • PostgreSQL • FAISS • Groq API</p>
          </footer>
        </section>

        <AuthHero />
      </div>
    </main>
  );
}
