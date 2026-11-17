import { Languages } from "lucide-react";
import type React from "react";
import { createContext, useContext, useEffect, useMemo, useState } from "react";
import { type LanguageOption, setRequestLanguage } from "./api";

// Kha nang cua mo hinh dang chay, lay tu /health: doc duoc nhung ngon ngu nao
// (Supertonic, Kokoro), co nhan ban giong va the cam xuc khong. Moi tab doc chung mot lua chon ngon
// ngu; api.ts tu gui kem no trong cac request doc.

interface ModelCaps {
  language: string;
  /** Ten ngon ngu dang chon de hien tren the giong ("Tiếng Anh"). */
  languageName: string;
  languages: LanguageOption[];
  /** Doc duoc tieng Viet khong (VieNeu, Supertonic: co; Kokoro: khong). Tu dien
   * phat am viet theo cach doc tieng Viet nen chi dung khi co. */
  readsVietnamese: boolean;
  /** Ngon ngu chon duoc o danh sach giong gop (hop cua moi mo hinh da tai). Chi co mo hinh
   * dang chay thi bang `languages`. */
  selectableLanguages: LanguageOption[];
  setLanguage: (code: string) => void;
  supportsCloning: boolean;
  supportsEmotions: boolean;
}

const MULTILINGUAL = "Đa ngôn ngữ";

/** Mo ta giong: "Nữ · Đa ngôn ngữ · …" -> "Nữ · Tiếng Anh · …" theo ngon ngu dang chon. */
export function describeVoice(
  description: string,
  languageName: string
): string {
  return languageName
    ? description.replace(MULTILINGUAL, languageName)
    : description;
}

const ModelCapsContext = createContext<ModelCaps>({
  language: "",
  languageName: "",
  languages: [],
  readsVietnamese: true,
  selectableLanguages: [],
  setLanguage: () => undefined,
  supportsCloning: true,
  supportsEmotions: true,
});

export function useModelCaps(): ModelCaps {
  return useContext(ModelCapsContext);
}

export const ModelCapsProvider: React.FC<{
  children: React.ReactNode;
  languages: LanguageOption[];
  /** Ngon ngu cua danh sach giong gop; khong truyen thi chi co ngon ngu cua mo hinh dang chay. */
  selectableLanguages?: LanguageOption[];
  supportsCloning: boolean;
  supportsEmotions: boolean;
}> = ({
  children,
  languages,
  selectableLanguages: union,
  supportsCloning,
  supportsEmotions,
}) => {
  // "" = tu nhan theo chu (hien moi giong). Chon mot ngon ngu thi danh sach giong loc theo no.
  const [language, setLanguage] = useState("");
  const selectableLanguages = union && union.length > 0 ? union : languages;

  useEffect(() => {
    // Chi gui cho API khi mo hinh dang chay doc duoc tieng do; chon tieng cua mo hinh khac
    // thi danh sach giong se chuyen sang mo hinh do (VoiceSelector).
    const valid = languages.some((l) => l.code === language);
    setRequestLanguage(valid ? language : null);
    if (language && !selectableLanguages.some((l) => l.code === language)) {
      setLanguage("");
    }
  }, [language, languages, selectableLanguages]);

  const languageName =
    selectableLanguages.find((l) => l.code === language)?.name ??
    "Tự nhận ngôn ngữ";
  const readsVietnamese =
    languages.length === 0 || languages.some((l) => l.code === "vi");
  const value = useMemo(
    () => ({
      language,
      languageName,
      languages,
      readsVietnamese,
      selectableLanguages,
      setLanguage,
      supportsCloning,
      supportsEmotions,
    }),
    [
      language,
      languageName,
      languages,
      readsVietnamese,
      selectableLanguages,
      supportsCloning,
      supportsEmotions,
    ]
  );
  return (
    <ModelCapsContext.Provider value={value}>
      {children}
    </ModelCapsContext.Provider>
  );
};

/** O chon ngon ngu doc; khong hien gi khi chi co mot ngon ngu de chon (VieNeu).
 * `scope="all"`: ngon ngu cua moi mo hinh da tai (o cot giong doc, chon xong tu chuyen giong/mo hinh);
 * mac dinh chi ngon ngu cua mo hinh dang chay (cac tab chi dung giong cua mo hinh do). */
export const LanguageSelect: React.FC<{
  className?: string;
  disabled?: boolean;
  scope?: "all" | "active";
}> = ({ className, disabled, scope = "active" }) => {
  const caps = useModelCaps();
  const { language, setLanguage } = caps;
  const languages = scope === "all" ? caps.selectableLanguages : caps.languages;
  if (
    languages.length === 0 ||
    (scope === "all" && languages.length < 2 && caps.languages.length === 0)
  ) {
    return null;
  }
  return (
    <label
      className={`flex items-center gap-2 text-xs ${className ?? ""}`}
      title="Chọn đúng tiếng của đoạn văn để đọc chuẩn giọng bản xứ (không dịch văn bản). Nút nghe thử cũng đọc câu mẫu bằng tiếng này. Tự nhận: có dấu tiếng Việt thì đọc tiếng Việt, chữ Nhật/Hàn thì đọc tiếng Nhật/Hàn, còn lại đọc tiếng Anh."
    >
      <Languages className="h-4 w-4 shrink-0 text-brand-500" />
      <span className="shrink-0 font-semibold text-foreground/90">
        Ngôn ngữ văn bản
      </span>
      <select
        className="w-full min-w-0 rounded-lg border border-border/80 bg-background px-2.5 py-1.5 outline-none focus:border-brand-500"
        disabled={disabled}
        onChange={(e) => setLanguage(e.target.value)}
        value={language}
      >
        <option value="">Tự nhận theo văn bản</option>
        {languages.map((l) => (
          <option key={l.code} value={l.code}>
            {l.name}
          </option>
        ))}
      </select>
    </label>
  );
};
