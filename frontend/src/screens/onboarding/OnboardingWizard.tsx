import { useParams, useNavigate, Navigate } from "react-router-dom";
import { cn } from "@/lib/cn";
import { Step1ProfileParse } from "./Step1ProfileParse";
import { Step2Roles } from "./Step2Roles";
import { Step3Companies } from "./Step3Companies";
import { Step4Scan } from "./Step4Scan";

const STEPS = [
  { number: 1, label: "Perfil" },
  { number: 2, label: "Cargos" },
  { number: 3, label: "Empresas" },
  { number: 4, label: "Escaneo" },
] as const;

export function OnboardingWizard() {
  const { step } = useParams<{ step: string }>();
  const navigate = useNavigate();
  const currentStep = Number(step);

  if (isNaN(currentStep) || currentStep < 1 || currentStep > 4) {
    return <Navigate to="/onboarding/1" replace />;
  }

  return (
    <div className="mx-auto flex min-h-screen max-w-4xl flex-col px-4 py-8">
      {/* Stepper */}
      <nav aria-label="Progreso del onboarding" className="mb-8">
        <ol className="flex items-center justify-center gap-2">
          {STEPS.map((s, idx) => (
            <li key={s.number} className="flex items-center">
              <button
                type="button"
                onClick={() => navigate(`/onboarding/${s.number}`)}
                disabled={s.number > currentStep}
                className={cn(
                  "flex h-8 w-8 items-center justify-center rounded-full text-sm font-medium transition-colors",
                  s.number === currentStep &&
                    "bg-primary-500 text-white",
                  s.number < currentStep &&
                    "bg-primary-100 text-primary-700",
                  s.number > currentStep &&
                    "bg-gray-100 text-gray-400 cursor-not-allowed",
                )}
                aria-current={s.number === currentStep ? "step" : undefined}
              >
                {s.number}
              </button>
              <span
                className={cn(
                  "ml-2 text-sm font-medium",
                  s.number === currentStep ? "text-primary-700" : "text-gray-500",
                )}
              >
                {s.label}
              </span>
              {idx < STEPS.length - 1 && (
                <div
                  className={cn(
                    "mx-3 h-px w-8",
                    s.number < currentStep ? "bg-primary-300" : "bg-gray-200",
                  )}
                />
              )}
            </li>
          ))}
        </ol>
      </nav>

      {/* Step content */}
      <div className="flex-1">
        {currentStep === 1 && <Step1ProfileParse />}
        {currentStep === 2 && <Step2Roles />}
        {currentStep === 3 && <Step3Companies />}
        {currentStep === 4 && <Step4Scan />}
      </div>
    </div>
  );
}
