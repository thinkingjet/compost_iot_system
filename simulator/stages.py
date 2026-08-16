"""The definition of the various compost stages that exist"""

STAGES = [
    {
        "id": 0,
        "name": "Early Mesophilic",
        "day_range": (0, 4),
        "temp_range": (20.0, 38.0),
        "moisture_range": (62.0, 75.0),
        "gas_range": (40.0, 90.0),
    },
    {
        "id": 1,
        "name": "Active Thermophilic",
        "day_range": (4, 14),
        "temp_range": (38.0, 65.0),
        "moisture_range": (48.0, 68.0),
        "gas_range": (90.0, 280.0),
    },
    {
        "id": 2,
        "name": "Peak Decomposition",
        "day_range": (14, 20),
        "temp_range": (52.0, 70.0),
        "moisture_range": (36.0, 52.0),
        "gas_range": (280.0, 580.0),
    },
    {
        "id": 3,
        "name": "Cooling",
        "day_range": (20, 28),
        "temp_range": (28.0, 55.0),
        "moisture_range": (38.0, 54.0),
        "gas_range": (120.0, 480.0),
    },
    {
        "id": 4,
        "name": "Maturation",
        "day_range": (28, 36),
        "temp_range": (24.0, 35.0),
        "moisture_range": (38.0, 52.0),
        "gas_range": (45.0, 160.0),
    },
    {
        "id": 5,
        "name": "Mature Compost",
        "day_range": (36, 42),
        "temp_range": (18.0, 28.0),
        "moisture_range": (34.0, 50.0),
        "gas_range": (20.0, 90.0),
    },
]
