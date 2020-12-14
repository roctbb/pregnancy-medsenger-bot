from flask_sqlalchemy import SQLAlchemy

db_string = "postgres://{}:{}@{}:{}/{}".format(DB_LOGIN, DB_PASSWORD, DB_HOST, DB_PORT, DB_DATABASE)
app.config['SQLALCHEMY_DATABASE_URI'] = db_string
db = SQLAlchemy(app)


class Order(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    start_order = db.Column(db.String(255))
    start_params = db.Column(db.Text, nullable=True)
    end_order = db.Column(db.String(255))
    end_params = db.Column(db.Text, nullable=True)
    start_week = db.Column(db.Integer, default=0)
    end_week = db.Column(db.Integer, nullable=True)
    after_birth = db.Column(db.Boolean, default=True)
    risks = db.relationship('Risk', secondary='order_risk')


class Risk(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(512))
    comment = db.Column(db.String(512))
    code = db.Column(db.String(512), nullable=True)


class OrderRisk(db.Model):
    order_id = db.Column(db.Integer, db.ForeignKey('order.id'), primary_key=True)
    risk_id = db.Column(db.Integer, db.ForeignKey('risk.id'), primary_key=True)


default_risks = [
    {
        "name": "риск ГВ",
        "comment": "",
        "code": "risk_gv"
    },
    {
        "name": "риск ВРТ",
        "comment": "",
        "code": "risk_vrt"
    },
    {
        "name": "риск ПЭ",
        "comment": "",
        "code": "risk_pe"
    },
    {
        "name": "риск СА",
        "comment": "",
        "code": "risk_sa"
    },
    {
        "name": "риск ПР",
        "comment": "",
        "code": "risk_pr"
    },
    {
        "name": "риск ГБП",
        "comment": "",
        "code": "risk_gbp"
    },
    {
        "name": "тошнота и рвота",
        "comment": "",
        "code": "voming"
    },
    {
        "name": "изжога",
        "comment": "",
        "code": "heartburn"
    },
    {
        "name": "геморрой",
        "comment": "",
        "code": "hemorrhoids"
    },
]

for risk in default_risks:
    object = Risk(name=risk['name'], comment=risk['comment'], code=risk['comment'])
    db.session.add(object)

timetable = {
    "days_month": [],
    "days_week": [],
    "hours": [{"value": 10}]
}

default_orders = [
    {
        "start_order": "enable_monitoring",
        "start_params": {
            "category": "temperature",
            "mode": "daily",
            "timetable": timetable,
            "min": 35,
            "max": 37.2
        },
        "end_order": "disable_monitoring",
        "end_params": {
            "category": "temperature",
        },
        "start_week": 0,
        "end_week": 44,
        "after_birth": True,
        "risks": []
    },
    {
        "start_order": "enable_monitoring",
        "start_params": {
            "category": "pressure",
            "mode": "daily",
            "timetable": {
                "days_month": [],
                "days_week": [],
                "hours": [{"value": 10}, {"value": 18}]
            },
            "max_systolic": 135,
            "min_systolic": 80,
            "max_diastolic": 85,
            "min_diastolic": 50,
            "max_pulse": 80,
            "min_pulse": 40
        },
        "end_order": "disable_monitoring",
        "end_params": {
            "category": "pressure",
        },
        "start_week": 0,
        "end_week": 44,
        "after_birth": True,
        "risks": []
    },
    {
        "start_order": "enable_monitoring",
        "start_params": {
            "category": "weight",
            "mode": "daily",
            "timetable": timetable,
            "min": 0,
            "max": 250
        },
        "end_order": "disable_monitoring",
        "end_params": {
            "category": "weight",
        },
        "start_week": 14,
        "end_week": 44,
        "after_birth": False,
        "risks": []
    },
    {
        "start_order": "enable_monitoring",
        "start_params": {
            "category": "waist_circumference",
            "mode": "monthly",
            "timetable": {
                "days_month": [],
                "days_week": [
                    {
                        "day": 1,
                        "hour": 10
                    }
                ],
                "hours": []
            },
            "min": 0,
            "max": 250
        },
        "end_order": "disable_monitoring",
        "end_params": {
            "category": "waist_circumference",
        },
        "start_week": 14,
        "end_week": 44,
        "after_birth": False,
        "risks": []
    },
    # medicines
    #name = data['params']['name']
    #mode = data['params']['mode']
    #dosage = data['params']['dosage']
    #amount = data['params']['amount']
    #timetable = json.dumps(data['params']['timetable'])
]

for order in default_orders:
    object = Order(start_order=order['start_order'], start_params=order['start_params'], end_order=order['end_order'], end_params=order['end_params'],
                   start_week=order['start_week'], end_week=order['end_week'], after_birth=order['after_birth'])

    db.session.add(object)

    for risk in order['risks']:
        object.risks.append(Risk.query.filter_by(code=risk).first())

db.session.commit()