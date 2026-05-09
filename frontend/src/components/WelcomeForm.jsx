import { useState, useEffect } from 'react';
import { createSession } from '../services/api';
import { Baby, X } from 'lucide-react';

const WelcomeForm = ({ onSessionCreated, onClose, initialData, sessionId }) => {
  const [formData, setFormData] = useState({
    tanggal_lahir: '',
    gender: '',
    nama_anak: '',
    berat_badan_kg: '',
    tinggi_badan_cm: '',
    topik: ''
  });
  
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    if (initialData) setFormData(initialData);
  }, [initialData]);

  const handleChange = (e) => {
    const { name, value } = e.target;
    setFormData(prev => ({ ...prev, [name]: value }));
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    setError('');
    
    try {
      // Kirim formData mentah, api.js yang akan bersihkan & validasi
      const response = await createSession(formData);
      onSessionCreated(response.session_id, formData);
    } catch (err) {
      console.error("❌ Session Error:", err);
      setError(err.message || 'Terjadi kesalahan saat menyimpan data.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="h-full bg-bg-secondary flex items-center justify-center p-6 overflow-y-auto">
      <div className="bg-bg-main w-full max-w-2xl rounded-2xl shadow-md border border-border overflow-hidden relative">
        <div className="p-6 border-b border-border flex items-center justify-between">
          <div>
            <h2 className="text-xl font-bold text-text-main">
              {sessionId ? 'Edit Data Bayi' : 'Selamat Datang di ParentEase'}
            </h2>
            <p className="text-text-muted text-sm">Asisten parenting cerdas</p>
          </div>
          {sessionId && (
            <button onClick={onClose} className="p-2 hover:bg-bg-tertiary rounded-full text-text-muted">
              <X className="w-5 h-5" />
            </button>
          )}
        </div>

        <div className="p-6">
          {error && (
            <div className="bg-red-50 text-red-600 p-3 rounded-lg mb-4 text-sm border border-red-100">
              {error}
            </div>
          )}

          <form onSubmit={handleSubmit} className="space-y-5">
            {/* Tanggal Lahir */}
            <div>
              <label className="block text-sm font-medium text-text-main mb-1.5">Tanggal Lahir Bayi *</label>
              <input 
                type="date" 
                name="tanggal_lahir"
                required
                value={formData.tanggal_lahir}
                onChange={handleChange}
                className="w-full px-4 py-2.5 rounded-lg border border-border bg-bg-tertiary focus:border-primary focus:ring-2 focus:ring-primary/20 outline-none transition"
              />
            </div>

            {/* Gender */}
            <div>
              <label className="block text-sm font-medium text-text-main mb-1.5">Jenis Kelamin *</label>
              <div className="flex gap-3">
                {['L', 'P'].map((g) => (
                  <button 
                    key={g} 
                    type="button"
                    onClick={() => setFormData({...formData, gender: g})}
                    className={`flex-1 py-2.5 px-4 rounded-lg border text-sm font-medium transition ${
                      formData.gender === g 
                        ? 'border-primary bg-primary-light text-primary' 
                        : 'border-border text-text-muted hover:bg-bg-tertiary'
                    }`}
                  >
                    {g === 'L' ? '👦 Laki-laki' : '👧 Perempuan'}
                  </button>
                ))}
              </div>
            </div>

            {/* Nama */}
            <div>
              <label className="block text-sm font-medium text-text-main mb-1.5">Nama Anak (Opsional)</label>
              <input 
                type="text" 
                name="nama_anak"
                value={formData.nama_anak}
                onChange={handleChange}
                placeholder="Misal: Aisyah"
                className="w-full px-4 py-2.5 rounded-lg border border-border bg-bg-tertiary focus:border-primary focus:ring-2 focus:ring-primary/20 outline-none transition"
              />
            </div>

            {/* Berat & Tinggi */}
            <div className="grid grid-cols-2 gap-5">
              <div>
                <label className="block text-sm font-medium text-text-main mb-1.5">Berat Badan (kg)</label>
                <input 
                  type="number" 
                  name="berat_badan_kg"
                  step="0.1"
                  value={formData.berat_badan_kg}
                  onChange={handleChange}
                  className="w-full px-4 py-2.5 rounded-lg border border-border bg-bg-tertiary focus:border-primary focus:ring-2 focus:ring-primary/20 outline-none transition"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-text-main mb-1.5">Tinggi Badan (cm)</label>
                <input 
                  type="number" 
                  name="tinggi_badan_cm"
                  step="0.1"
                  value={formData.tinggi_badan_cm}
                  onChange={handleChange}
                  className="w-full px-4 py-2.5 rounded-lg border border-border bg-bg-tertiary focus:border-primary focus:ring-2 focus:ring-primary/20 outline-none transition"
                />
              </div>
            </div>

            <button 
              type="submit" 
              disabled={loading}
              className="w-full bg-primary text-white py-3 rounded-lg font-semibold hover:bg-primary-hover transition disabled:opacity-50 flex items-center justify-center gap-2 mt-4 shadow-md shadow-primary/20"
            >
              <Baby className="w-5 h-5" />
              {loading ? 'Menyimpan...' : (sessionId ? 'Simpan Perubahan' : 'Mulai Konsultasi')}
            </button>
          </form>
        </div>
      </div>
    </div>
  );
};

export default WelcomeForm;