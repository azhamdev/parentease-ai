// frontend/src/services/api.js
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

export const sendMessage = async (sessionId, message) => {
  const res = await fetch(`${API_URL}/chat`, {
    method: "POST",
    headers: { 
      "Content-Type": "application/json",
      "X-Session-ID": sessionId
    },
    body: JSON.stringify({ message }),
  });
  
  if (!res.ok) {
    throw new Error("Gagal mengirim pesan");
  }
  
  const data = await res.json();

  return {
    response: data.response,
    sources: data.sources || []  // Simpan sources
  };
};