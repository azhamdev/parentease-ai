const API_URL = import.meta.env.VITE_API_URL || "/api/v1";

const normalizeDate = (value) => {
  if (!value) return value;
  if (/^\d{4}-\d{2}-\d{2}$/.test(value)) return value;

  const slashMatch = value.match(/^(\d{1,2})\/(\d{1,2})\/(\d{4})$/);
  if (slashMatch) {
    const [, day, month, year] = slashMatch;
    return `${year}-${month.padStart(2, "0")}-${day.padStart(2, "0")}`;
  }

  return value;
};

const parseOptionalNumber = (value) => {
  if (value === undefined || value === null || value === "") return undefined;
  return parseFloat(String(value).replace(",", "."));
};


export const createSession = async (data) => {
  const tanggalLahir = normalizeDate(data.tanggal_lahir);
  // 1. Validasi wajib sebelum request
  if (!tanggalLahir || !data.gender) {
    throw new Error("Tanggal lahir dan gender wajib diisi");
  }
  
  // 2. Bangun payload bersih
  const payload = {
    tanggal_lahir: tanggalLahir,
    gender: data.gender.toUpperCase(), // "L" atau "P"
    nama_anak: data.nama_anak || undefined,
    berat_badan_kg: parseOptionalNumber(data.berat_badan_kg),
    tinggi_badan_cm: parseOptionalNumber(data.tinggi_badan_cm),
    topik: data.topik || undefined,
  };
  
  console.log("📤 Payload dikirim:", JSON.stringify(payload, null, 2));
  
  const res = await fetch(`${API_URL}/profiles/`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  
  if (!res.ok) {
    const errData = await res.json();
    console.error("❌ Backend error detail:", errData);
    const msg = errData.detail?.[0]?.msg || errData.detail || "Gagal membuat session";
    throw new Error(msg);
  }
  return res.json();
};

export const sendMessage = async (sessionId, message, onChunk) => {
  const res = await fetch(`${API_URL}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-Session-ID": sessionId },
    body: JSON.stringify({ message }),
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let fullResponse = "";
  let sources = [];
  let lastChar = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop();

    for (const line of lines) {
      // ✅ SKIP baris kosong
      if (line === "") continue;
      
      let data = "";
      
      // ✅ FIX: Parse SSE format "data: {content}"
      if (line.startsWith("data: ")) {
        data = line.slice(6); // Hapus prefix "data: "
      } else {
        // Fallback untuk kompatibilitas, termasuk marker [SOURCES] yang bisa
        // muncul di baris berikutnya setelah token newline.
        data = line;
      }
      
      // ✅ SKIP jika data kosong
      if (data === "") continue;

      const clean = data.trim();
      if (clean === "[DONE]") break;
      if (clean.startsWith("[ERROR]")) throw new Error(clean.slice(9));
      if (clean.startsWith("[SOURCES]")) {
        try { sources = JSON.parse(clean.replace(/^\[SOURCES\]\s*/, "")); } catch { sources = []; }
        continue;
      }
      
     // ✅ AUTO-SPACE: Tambah spasi setelah tanda baca jika token berikutnya tidak dimulai spasi
      if (lastChar && /[!.,:;]/.test(lastChar) && data && !data.startsWith(" ") && !data.startsWith("\n")) {
        fullResponse += " ";
        onChunk(" ");
      }
      
      // ✅ Tambahkan ke response
      fullResponse += data;
      onChunk(data);
      
      // ✅ Update lastChar dengan karakter terakhir dari data
      if (data) {
        lastChar = data[data.length - 1];
      }
    }
  }

  const inlineSourcesMatch = fullResponse.match(/\[SOURCES\]\s*(\[[\s\S]*?\])/);
  if (inlineSourcesMatch) {
    try {
      sources = JSON.parse(inlineSourcesMatch[1]);
      fullResponse = fullResponse.replace(/\[SOURCES\]\s*\[[\s\S]*?\]/, "").trim();
    } catch {
      sources = [];
    }
  }

  return { response: fullResponse, sources };
};

export const updateChildProfile = async (sessionId, data) => {
  const tanggalLahir = normalizeDate(data.tanggal_lahir);
  // Validasi format tanggal
  if (!tanggalLahir) {
    throw new Error("Tanggal lahir wajib diisi");
  }
  
  // Pastikan format YYYY-MM-DD
  const datePattern = /^\d{4}-\d{2}-\d{2}$/;
  if (!datePattern.test(tanggalLahir)) {
    throw new Error("Format tanggal lahir harus YYYY-MM-DD");
  }
  
  // Bangun payload bersih
  const payload = {
    nama_anak: data.nama_anak?.trim() || undefined,
    tanggal_lahir: tanggalLahir,
    gender: data.gender?.toUpperCase() || undefined,
    berat_badan_kg: parseOptionalNumber(data.berat_badan_kg),
    tinggi_badan_cm: parseOptionalNumber(data.tinggi_badan_cm),
  };
  
  console.log("📤 Update payload:", JSON.stringify(payload, null, 2));
  
  // ✅ FIX: Endpoint yang benar adalah /profiles/{sessionId}
  const res = await fetch(`${API_URL}/profiles/${sessionId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    console.error("❌ Update error:", err);
    throw new Error(err.detail || "Gagal memperbarui data anak");
  }
  return res.json();
};

export const getChildProfile = async (sessionId) => {
  const res = await fetch(`${API_URL}/profiles/${sessionId}`, {
    method: "GET",
    headers: { 
      "Content-Type": "application/json",
      "Accept": "application/json"
    },
  });
  
  if (!res.ok) {
    const errData = await res.json().catch(() => ({}));
    throw new Error(errData.detail || "Gagal memuat data anak");
  }
  return res.json();
};

export const getSessions = async () => {
  const url = `${API_URL}/sessions`.replace(/\/+$/, '');
  const res = await fetch(url, {
    method: "GET",
    headers: { "Content-Type": "application/json", "Accept": "application/json" },
  });
  if (!res.ok) {
    const errData = await res.json().catch(() => ({}));
    throw new Error(errData.detail || `HTTP error! status: ${res.status}`);
  }
  return res.json();
};

export const getMessages = async (sessionId) => {
  const url = `${API_URL}/sessions/${sessionId}/messages`.replace(/\/+$/, '');
  const res = await fetch(url, {
    method: "GET",
    headers: { "Content-Type": "application/json", "Accept": "application/json" },
    mode: "cors",
  });
  if (!res.ok) {
    const errData = await res.json().catch(() => ({}));
    throw new Error(errData.detail || `HTTP error! status: ${res.status}`);
  }
  return res.json();
};

export const deleteSession = async (sessionId) => {
  const res = await fetch(`${API_URL}/sessions/${sessionId}`, {
    method: "DELETE",
    headers: { "Content-Type": "application/json" },
  });
  
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || "Gagal menghapus session");
  }
  return res.json();
};

export const uploadPDF = async (sessionId, file, message, onChunk) => {
  const formData = new FormData();
  formData.append("file", file);
  if (message) formData.append("message", message);

  const res = await fetch(`${API_URL}/chat/upload-pdf`, {
    method: "POST",
    headers: { "X-Session-ID": sessionId },
    body: formData,
  });
  if (!res.ok) {
    const errData = await res.json().catch(() => ({}));
    throw new Error(errData.detail || `Upload failed: HTTP ${res.status}`);
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let fullResponse = "";
  let sources = [];
  let lastChar = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop();

    for (const line of lines) {
      if (line === "") continue;

      let data = "";
      if (line.startsWith("data: ")) {
        data = line.slice(6);
      } else {
        data = line;
      }
      if (data === "") continue;

      const clean = data.trim();
      if (clean === "[DONE]") break;
      if (clean.startsWith("[ERROR]")) throw new Error(clean.slice(9));
      if (clean.startsWith("[SOURCES]")) {
        try { sources = JSON.parse(clean.replace(/^\[SOURCES\]\s*/, "")); } catch { sources = []; }
        continue;
      }

      if (lastChar && /[!.,:;]/.test(lastChar) && data && !data.startsWith(" ") && !data.startsWith("\n")) {
        fullResponse += " ";
        onChunk(" ");
      }

      fullResponse += data;
      onChunk(data);

      if (data) {
        lastChar = data[data.length - 1];
      }
    }
  }

  const inlineSourcesMatch = fullResponse.match(/\[SOURCES\]\s*(\[[\s\S]*?\])/);
  if (inlineSourcesMatch) {
    try {
      sources = JSON.parse(inlineSourcesMatch[1]);
      fullResponse = fullResponse.replace(/\[SOURCES\]\s*\[[\s\S]*?\]/, "").trim();
    } catch {
      sources = [];
    }
  }

  return { response: fullResponse, sources };
};
