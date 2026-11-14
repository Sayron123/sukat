"use client";

import { useState } from "react";

import { PASSWORD_RULES, suggestPassword } from "@/lib/password";

import { Icon } from "./icons";
import { PasswordField } from "./password-field";
import { textLinkClass } from "./ui";

export function NewPasswordFields({
  name,
  label,
  confirmLabel = "Confirm password",
  onSuggest,
}: {
  name: string;
  label: string;
  confirmLabel?: string;
  onSuggest: () => void;
}) {
  const [value, setValue] = useState("");
  const [confirm, setConfirm] = useState("");
  const [suggested, setSuggested] = useState(false);

  function suggest() {
    const password = suggestPassword();
    setValue(password);
    setConfirm(password);
    setSuggested(true);
    onSuggest();
  }

  return (
    <div className="flex flex-col gap-[22px]">
      <div>
        <PasswordField
          key={suggested ? "suggested" : "typed"}
          id={name}
          name={name}
          label={label}
          autoComplete="new-password"
          maxLength={128}
          required
          startVisible={suggested}
          value={value}
          onChange={(e) => setValue(e.target.value)}
        />
        <ul className="mt-2 grid grid-cols-2 gap-x-3 gap-y-1">
          {PASSWORD_RULES.map((rule) => {
            const met = rule.met(value);
            return (
              <li key={rule.label} className={`flex items-center gap-1.5 text-[13px] ${met ? "text-text" : "text-muted"}`}>
                <span className="grid h-4 w-4 shrink-0 place-items-center">
                  {met ? (
                    <Icon name="check" size={14} className="text-green-text" />
                  ) : (
                    <span className="h-3 w-3 rounded-full border-[1.5px] border-muted" />
                  )}
                </span>
                <span className="sr-only">{met ? "Done:" : "Needed:"}</span>
                {rule.label}
              </li>
            );
          })}
        </ul>
        <button type="button" onClick={suggest} className={textLinkClass}>
          Suggest a password for me
        </button>
        {suggested && (
          <p role="status" className="text-[13px] leading-snug text-muted">
            Keep a copy of this password. Your browser may offer to save it when you finish.
          </p>
        )}
      </div>
      <PasswordField
        key={suggested ? "confirm-suggested" : "confirm-typed"}
        id="confirm_password"
        name="confirm_password"
        label={confirmLabel}
        autoComplete="new-password"
        required
        startVisible={suggested}
        value={confirm}
        onChange={(e) => setConfirm(e.target.value)}
      />
    </div>
  );
}
