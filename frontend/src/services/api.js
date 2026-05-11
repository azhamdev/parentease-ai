const API_URL = "http://localhost:8000";

export const createSession = async (data) => {
  // 1. Validasi wajib sebelum request
  if (!data.tanggal_lahir || !data.gender) {
    throw new Error("Tanggal lahir dan gender wajib diisi");
  }

  // 2. Bangun payload bersih (hapus field kosong/invalid)
  const payload = {
    context: {
      tanggal_lahir: data.tanggal_lahir, // Harus format "YYYY-MM-DD"
      gender: data.gender.toUpperCase(), // "L" atau "P"
      nama_anak: data.nama_anak || undefined,
      berat_badan_kg: data.berat_badan_kg ? parseFloat(data.berat_badan_kg) : undefined,
      tinggi_badan_cm: data.tinggi_badan_cm ? parseFloat(data.tinggi_badan_cm) : undefined,
      topik: data.topik || undefined,
    }
  };

  console.log("📤 Payload dikirim:", JSON.stringify(payload, null, 2));

  const res = await fetch(`${API_URL}/sessions`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });

  if (!res.ok) {
    const errData = await res.json();
    console.error("❌ Backend 422 Detail:", errData);
    // Ambil pesan error yang paling relevan
    const msg = errData.detail?.[0]?.msg || "Gagal membuat session";
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
        // Fallback untuk kompatibilitas
        data = line;
      }
      
      // ✅ SKIP jika data kosong
      if (data === "") continue;

      const clean = data.trim();
      if (clean === "[DONE]") break;
      if (clean.startsWith("[ERROR]")) throw new Error(clean.slice(9));
      if (clean.startsWith("[SOURCES] ")) {
        try { sources = JSON.parse(clean.slice(10)); } catch { sources = []; }
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

  return { response: fullResponse, sources };
};

export const getSessions = async () => {
  const res = await fetch(`${API_URL}/sessions`);
  if (!res.ok) throw new Error("Gagal memuat riwayat chat");
  return res.json();
};

export const getMessages = async (sessionId) => {
  const res = await fetch(`${API_URL}/sessions/${sessionId}/messages`);
  if (!res.ok) throw new Error("Gagal memuat pesan");
  return res.json();
};