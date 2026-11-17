// Panel «Hoy»: saludo según la hora, reloj, clima, próximo recordatorio y titulares.
import { useEffect, useState } from "react";
import { api, relativeTime, usePolled, type Headline, type Personality, type Reminder, type Weather } from "./api";
import { Glyph } from "./Glyph";

export function greeting(hour: number): string {
  if (hour >= 5 && hour < 12) return "Buenos días";
  if (hour >= 12 && hour < 19) return "Buenas tardes";
  return "Buenas noches";
}

function useClock() {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const timer = window.setInterval(() => setNow(new Date()), 1000);
    return () => window.clearInterval(timer);
  }, []);
  return now;
}

export function TodayPanel({ personality, online, onAsk, onOpenSettings }: { personality: Personality | null; online: boolean; onAsk: (prompt: string) => void; onOpenSettings: () => void }) {
  const now = useClock();
  const city = personality?.home_city ?? "";
  const weather = usePolled(() => api<Weather>("GET", "/widgets/weather"), 15 * 60_000, online && Boolean(city));
  const news = usePolled(() => api<Headline[]>("GET", "/widgets/news", { query: { limit: 4 } }), 20 * 60_000, online);
  const reminders = usePolled(() => api<Reminder[]>("GET", "/reminders"), 60_000, online);
  // Al cambiar la ciudad en Configuración, el clima se vuelve a pedir.
  const reloadWeather = weather.reload;
  useEffect(() => { if (online && city) void reloadWeather(); }, [city, online, reloadWeather]);

  const name = personality?.user_name ? `, ${personality.user_name}` : "";
  const next = reminders.data?.[0];
  const w = weather.data;

  return (
    <div className="today">
      <section className="today-hero">
        <div>
          <p className="today-greeting">{greeting(now.getHours())}{name}</p>
          <p className="today-date">{now.toLocaleDateString("es", { weekday: "long", day: "numeric", month: "long" })}</p>
        </div>
        <time className="today-clock">{now.toLocaleTimeString("es", { hour: "2-digit", minute: "2-digit" })}<small>{String(now.getSeconds()).padStart(2, "0")}</small></time>
      </section>

      <section className="today-card weather-card">
        {!city ? (
          <button className="today-empty" onClick={onOpenSettings}>
            <Glyph name="partly" size={26} /><span><b>Configura tu ciudad</b><small>Para ver el clima aquí: Configuración → Personalidad.</small></span>
          </button>
        ) : w ? (
          <>
            <div className="weather-now">
              <Glyph name={w.icon} size={44} className={`wx wx-${w.icon}`} />
              <div>
                <b className="weather-temp">{Math.round(w.temperature_c)}°</b>
                <span className="weather-desc">{w.description}</span>
                <small className="weather-place">{w.place.split(",")[0]}</small>
              </div>
              <ul className="weather-meta">
                <li><Glyph name="sun" size={13} />Sensación {Math.round(w.feels_like_c)}°</li>
                <li><Glyph name="drop" size={13} />{w.humidity} %</li>
                <li><Glyph name="wind" size={13} />{Math.round(w.wind_kmh)} km/h</li>
              </ul>
            </div>
            <ol className="weather-days">
              {w.days.slice(1, 4).map((day) => (
                <li key={day.date} title={day.description}>
                  <span>{day.day_name}</span>
                  <Glyph name={day.icon} size={20} className={`wx wx-${day.icon}`} />
                  <b>{Math.round(day.max_c)}°</b><small>{Math.round(day.min_c)}°</small>
                  {day.rain_chance ? <em>{day.rain_chance} %</em> : <em />}
                </li>
              ))}
            </ol>
          </>
        ) : (
          <p className="today-muted">{weather.error || (online ? "Consultando el clima…" : "Sin conexión con ATLAS.")}</p>
        )}
      </section>

      <section className="today-card">
        <header><Glyph name="clock" size={14} /> Próximo recordatorio</header>
        {next ? (
          <p className="today-reminder"><b>{next.message}</b><small>{relativeTime(next.due_at)}</small></p>
        ) : (
          <button className="today-link" onClick={() => onAsk("Recuérdame ")}>Sin recordatorios · crear uno</button>
        )}
      </section>

      <section className="today-card">
        <header><Glyph name="news" size={14} /> Titulares <button className="today-link right" onClick={() => onAsk("Dame las noticias más importantes de hoy")}>Resumir</button></header>
        {news.data?.length ? (
          <ul className="today-news">
            {news.data.map((h) => (
              <li key={h.url || h.title}><button onClick={() => onAsk(`Cuéntame más sobre esta noticia: «${h.title}»`)}>{h.title}</button><small>{h.source}{h.published ? ` · ${h.published.split(" ")[1] ?? ""}` : ""}</small></li>
            ))}
          </ul>
        ) : (
          <p className="today-muted">{news.error || (online ? "Cargando titulares…" : "Sin conexión con ATLAS.")}</p>
        )}
      </section>
    </div>
  );
}
