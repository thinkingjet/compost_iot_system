const hours = Array.from({ length: 24 }, (_, i) => `${String(i).padStart(2, "0")}:00`);

function series(base, amplitude, phase = 0, trend = 0) {
  return hours.map((_, index) => Number((base + Math.sin((index + phase) / 3.1) * amplitude + Math.cos((index + phase) / 1.9) * amplitude * 0.25 + index * trend).toFixed(2)));
}

export const telemetry = {
  time: hours,
  temperature: series(48, 5.4, 0, 0.28),
  moisture: series(57, 4.2, 3, -0.22),
  oxygen: series(19.6, 1.7, 5, 0.02),
  co2: series(2.3, 0.65, 2, 0.018),
};

export const historical = {
  dates: Array.from({ length: 36 }, (_, i) => `Day ${i + 1}`),
  temperature: Array.from({ length: 36 }, (_, i) => Number((24 + 42 * Math.exp(-Math.pow((i - 7) / 8, 2)) + Math.sin(i / 2.4) * 1.5).toFixed(1))),
  health: Array.from({ length: 36 }, (_, i) => Number(Math.min(94, 51 + i * 1.05 + Math.sin(i / 4) * 5).toFixed(1))),
};

export const metrics = [
  { label: "Temperature", value: "54.2", unit: "°C", delta: "+2.4%", icon: "temp", color: "red", values: telemetry.temperature },
  { label: "Moisture", value: "50.7", unit: "%", delta: "Within target", icon: "drop", color: "blue", values: telemetry.moisture },
  { label: "Oxygen", value: "20.4", unit: "%", delta: "+0.8%", icon: "wind", color: "green", values: telemetry.oxygen },
  { label: "Compost health", value: "86", unit: "/ 100", delta: "Optimal", icon: "activity", color: "lime", values: historical.health.slice(-24) },
];

export const bins = [
  { id: "bin-1", name: "Bin 1", location: "UNRAM", devices: 2, phase: "Peak decomposition", health: 86 },
  { id: "bin-3", name: "Bin 3", location: "Mataram", devices: 1, phase: "Active thermophilic", health: 74, variant: "blue" },
  { id: "school", name: "Primary School", location: "Lombok", devices: 1, phase: "Cooling", health: 68 },
];

export const devices = [
  { id: "outer", name: "Outer Sensor", location: "Bin 1", reading: "54.2°C", model: "ESP32-C3" },
  { id: "inner", name: "Inner Sensor", location: "Bin 1", reading: "52.8°C", model: "ESP32-C3" },
  { id: "school-device", name: "School Compost", location: "Primary School", reading: "41.6°C", model: "ESP8266" },
];

export const maintenanceTasks = [
  { title: "Temperature reaching high point", detail: "Turn the compost to maintain an even breakdown.", time: "In 2 hours" },
  { title: "Moisture will fall below target", detail: "Add approximately 3 litres of water.", time: "In 2 days" },
  { title: "Transition to maturation phase", detail: "The compost is progressing normally.", time: "In 10 days" },
];
