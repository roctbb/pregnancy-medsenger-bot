import json
import time
from threading import Thread
from flask import Flask, request, render_template
from config import *
import threading
import datetime
from flask_sqlalchemy import SQLAlchemy
import agents_api
import os, sys

app = Flask(__name__)
db_string = "postgres://{}:{}@{}:{}/{}".format(DB_LOGIN, DB_PASSWORD, DB_HOST, DB_PORT, DB_DATABASE)
app.config['SQLALCHEMY_DATABASE_URI'] = db_string
db = SQLAlchemy(app)


class Risk(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(512))
    comment = db.Column(db.String(512), nullable=True)
    code = db.Column(db.String(512), nullable=True)


class Order(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    start_order = db.Column(db.String(255))
    start_params = db.Column(db.JSON, nullable=True)
    end_order = db.Column(db.String(255))
    end_params = db.Column(db.JSON, nullable=True)
    start_week = db.Column(db.Integer, default=0)
    end_week = db.Column(db.Integer, nullable=True)
    after_birth = db.Column(db.Boolean, default=True)
    risks = db.relationship('Risk', secondary='order_risk')
    comment = db.Column(db.Text, nullable=True)

    def run(self, contract):
        return agents_api.send_order(contract.id, self.start_order, MONITORING_ID, self.start_params) == 1

    def stop(self, contract):
        return agents_api.send_order(contract.id, self.end_order, MONITORING_ID, self.end_params) == 1


class Contract(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    active = db.Column(db.Boolean, default=True)
    is_born = db.Column(db.Boolean, default=False)
    start = db.Column(db.Integer, nullable=True)
    created_on = db.Column(db.DateTime, server_default=db.func.now())
    updated_on = db.Column(db.DateTime, server_default=db.func.now(), server_onupdate=db.func.now())

    current_orders = db.relationship('Order', secondary='current_order')
    done_orders = db.relationship('Order', secondary='done_order')
    risks = db.relationship('Risk', secondary='contract_risk')

    def week(self):
        if not self.start:
            return None
        return int((time.time() - self.start) // (60 * 60 * 24 * 7))

    def remove_order(self, order):
        if order.stop(self):
            self.current_orders.remove(order)
            self.done_orders.append(order)
            return True
        return False

    def add_order(self, order):
        if order.run(self):
            self.current_orders.append(order)
            return True
        return False

    def check_risks(self, order):
        if not order.risks:
            return True

        for risk in self.risks:
            if risk in order.risks:
                return True

        return False

    def check_orders(self):

        try:
            new_orders = []
            old_orders = []

            if not self.week():
                return

            for order in self.current_orders:
                criteria = [self.is_born and not order.after_birth, order.end_week and self.week() > order.end_week,self.week() < order.start_week,
                            not self.check_risks(order)]
                if True in criteria and self.remove_order(order):
                    old_orders.append(order.comment)

            for order in Order.query.all():
                if order in self.current_orders:
                    continue

                if self.is_born and not order.after_birth:
                    continue

                if order.after_birth and self.is_born and self.check_risks(order) and self.add_order(order):
                        new_orders.append(order.comment)
                elif self.week() >= order.start_week and self.week() <= order.end_week and self.check_risks(
                            order) and self.add_order(order):
                        new_orders.append(order.comment)
            if new_orders + old_orders:
                send_orders_warning(self, new_orders, old_orders)

            db.session.commit()
        except Exception as e:
            exc_type, exc_obj, exc_tb = sys.exc_info()
            fname = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
            print(exc_type, fname, exc_tb.tb_lineno)
            print(e)

    def check_measurements(self):

        # control weight
        time_to = int(time.time()) - 60 * 60 * 24 * 4
        time_from = int(time.time()) - 60 * 60 * 24 * 11

        start_time = int(time.time()) - 60 * 60

        if self.week() >= 14 and not self.is_born:

            # control weight
            try:
                last_value = agents_api.get_records(self.id, 'weight', limit=1, time_from=start_time)['values'][0]['value']
                week_value = [record['value'] for record in
                              agents_api.get_records(self.id, 'weight', time_from=time_from, time_to=time_to)['values']]

                delta = last_value - sum(week_value) / len(week_value)
                if delta >= 1:
                    send_warning_to_doctor(self.id,
                                           "Предупреждение: последнее значение веса ({} кг) беременной превышает среднее за прошлую неделю ({} кг) на {} кг.".format(
                                               last_value, week_value, delta))

            except Exception as e:
                exc_type, exc_obj, exc_tb = sys.exc_info()
                fname = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
                print(exc_type, fname, exc_tb.tb_lineno)
                print(e)

            try:
                last_value = \
                    agents_api.get_records(self.id, 'waist_circumference', limit=2, time_from=start_time)['values'][0][
                        'value']
                week_value = [record['value'] for record in
                              agents_api.get_records(self.id, 'waist_circumference', time_from=time_from, time_to=time_to)[
                                  'values']]

                if week_value:
                    delta = last_value - sum(week_value) / len(week_value)
                    if delta <= 1:
                        send_warning_to_doctor(self.id,
                                               "Предупреждение: последнее обхвата талии ({} см) беременной по сравнению со средним за прошлую неделю ({} см) изменилось всего на {} см.".format(
                                                   last_value, week_value, delta))


            except Exception as e:
                print(e)


class CurrentOrder(db.Model):
    contract_id = db.Column(db.Integer, db.ForeignKey('contract.id'), primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('order.id'), primary_key=True)
    created_on = db.Column(db.DateTime, server_default=db.func.now())
    updated_on = db.Column(db.DateTime, server_default=db.func.now(), server_onupdate=db.func.now())


class DoneOrder(db.Model):
    contract_id = db.Column(db.Integer, db.ForeignKey('contract.id'), primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('order.id'), primary_key=True)
    created_on = db.Column(db.DateTime, server_default=db.func.now())
    updated_on = db.Column(db.DateTime, server_default=db.func.now(), server_onupdate=db.func.now())


class ContractRisk(db.Model):
    contract_id = db.Column(db.Integer, db.ForeignKey('contract.id'), primary_key=True)
    risk_id = db.Column(db.Integer, db.ForeignKey('risk.id'), primary_key=True)


class OrderRisk(db.Model):
    order_id = db.Column(db.Integer, db.ForeignKey('order.id'), primary_key=True)
    risk_id = db.Column(db.Integer, db.ForeignKey('risk.id'), primary_key=True)


try:
    db.create_all()
except:
    print('cant create structure')


def delayed(delay, f, args):
    timer = threading.Timer(delay, f, args=args)
    timer.start()


def check_digit(number, borders=None):
    try:
        n = int(number)

        if borders:
            if n < borders[0] or n > borders[1]:
                return False
        return True
    except:
        return False


def get_start(week):
    return int(time.time() - week * 7 * 24 * 60 * 60)


def gts():
    now = datetime.datetime.now()
    return now.strftime("%Y-%m-%d %H:%M:%S")


@app.route('/status', methods=['POST'])
def status():
    data = request.json

    if data['api_key'] != APP_KEY:
        return 'invalid key'

    contract_ids = [l[0] for l in db.session.query(Contract.id).all()]

    answer = {
        "is_tracking_data": True,
        "supported_scenarios": ['pregnancy'],
        "tracked_contracts": contract_ids
    }
    print(answer)

    return json.dumps(answer)


@app.route('/init', methods=['POST'])
def init():
    data = request.json

    if data['api_key'] != APP_KEY:
        return 'invalid key'

    try:
        contract_id = int(data['contract_id'])
        query = Contract.query.filter_by(id=contract_id)
        if query.count() != 0:
            contract = query.first()
            contract.active = True

            print("{}: Reactivate contract {}".format(gts(), contract.id))
        else:
            contract = Contract(id=contract_id, )
            db.session.add(contract)

            print("{}: Add contract {}".format(gts(), contract.id))

        if data.get('preset', None) == 'pregnancy':
            for param, value in data.get('params', {}).items():
                if param == 'week' and check_digit(value) and int(value) >= 0 and int(value) <= 40:
                    contract.week = get_start(int(value))

                if value == True:
                    risk = Risk.query.filter_by(code=param).first()
                    if risk:
                        contract.risks.append(risk)

        db.session.commit()
        contract.check_orders()


    except Exception as e:
        print(e)
        return "error"

    print('sending ok')
    return 'ok'


@app.route('/remove', methods=['POST'])
def remove():
    data = request.json

    if data['api_key'] != APP_KEY:
        print('invalid key')
        return 'invalid key'

    try:
        contract_id = str(data['contract_id'])
        contract = Contract.query.filter_by(id=contract_id).first()

        if contract:
            contract.active = False
            db.session.commit()

            print("{}: Deactivate contract {}".format(gts(), contract.id))
        else:
            print('contract not found')

    except Exception as e:
        print(e)
        return "error"

    return 'ok'


@app.route('/settings', methods=['GET'])
def settings():
    key = request.args.get('api_key', '')

    if key != APP_KEY:
        return "<strong>Некорректный ключ доступа.</strong> Свяжитесь с технической поддержкой."

    try:
        contract_id = int(request.args.get('contract_id'))
        query = Contract.query.filter_by(id=contract_id)
        if query.count() != 0:
            contract = query.first()
        else:
            return "<strong>Ошибка. Контракт не найден.</strong> Попробуйте отключить и снова подключить интеллектуальный агент к каналу консультирвоания.  Если это не сработает, свяжитесь с технической поддержкой."

    except Exception as e:
        exc_type, exc_obj, exc_tb = sys.exc_info()
        fname = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
        print(exc_type, fname, exc_tb.tb_lineno)
        print(e)
        return "error"

    return render_template('settings.html', contract=contract, risks=Risk.query.all())


@app.route('/settings', methods=['POST'])
def setting_save():
    key = request.args.get('api_key', '')

    if key != APP_KEY:
        return "<strong>Некорректный ключ доступа.</strong> Свяжитесь с технической поддержкой."

    try:
        contract_id = int(request.args.get('contract_id'))
        contract = Contract.query.filter_by(id=contract_id).first()
        if contract:
            week = request.form.get('week')
            if "is_born" in request.form:
                contract.is_born = True

            if week and check_digit(week) and int(week) >= 0 and int(week) <= 40:
                contract.start = get_start(int(week))
            if request.form.get('is_born'):
                contract.is_born = True

            for risk in Risk.query.all():
                if "risk_{}".format(risk.id) in request.form:
                    if risk not in contract.risks:
                        contract.risks.append(risk)
                else:
                    if risk in contract.risks:
                        contract.risks.remove(risk)

            contract.check_orders()
        else:
            return "<strong>Ошибка. Контракт не найден.</strong> Попробуйте отключить и снова подключить интеллектуальный агент к каналу консультирвоания.  Если это не сработает, свяжитесь с технической поддержкой."

    except Exception as e:
        exc_type, exc_obj, exc_tb = sys.exc_info()
        fname = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
        print(exc_type, fname, exc_tb.tb_lineno)
        print(e)
        return "error"

    return """
        <strong>Спасибо, окно можно закрыть</strong><script>window.parent.postMessage('close-modal-success','*');</script>
        """


@app.route('/', methods=['GET'])
def index():
    return 'waiting for the thunder!'


def send_warning_to_doctor(contract_id, a):
    try:
        agents_api.send_message(contract_id, text=a, is_urgent=True, only_doctor=True, need_answer=True)
    except Exception as e:
        print('connection error', e)


def send_orders_warning(contract, a, b):
    try:
        message = "В соответствии с протоколом ведения беременности "
        if a:
            message += "выполнены следующие назначения:\n - {}\n\n".format('\n - '.join(a))
        if a and b:
            message += "Также "
        if b:
            message += "отменены:\n - {}\n\n".format('\n - '.join(b))

        doctor_message = message + 'Изменить назначения можно в настройках интеллектуального агента "Мониторинг медицинских измерений и приема препаратов". <a href="https://drive.google.com/file/d/1PM4qWP2Cfm1p5W2fqbFC8iZahe5nhtjB/view?usp=sharing">Подробная схема мониторинга.</a>'
        patient_message = message + 'Если у вас возникнут вопросы, их можно задать вашему лечащему врачу в чате.'

        agents_api.send_message(contract.id, text=doctor_message, only_doctor=True)
        agents_api.send_message(contract.id, text=patient_message, only_patient=True)
    except Exception as e:
        print('connection error', e)


def send_warning(contract_id, a):
    try:
        if a:
            agents_api.send_message(contract_id,
                                    text="Беременная сообщила о следующих симптомах - {}.".format(' / '.join(a)),
                                    is_urgent=True, only_doctor=True, need_answer=True)
            agents_api.send_message(contract_id,
                                    text="Спасибо за заполнение опросника! Мы уведомили вашего врача о симптомах, которые вызывают беспокойство на вашем сроке беременности ({}). Он свяжется с вами в ближайшее время.".format(' / '.join(a)),
                                    is_urgent=True, only_patient=True)
        else:
            agents_api.send_message(contract_id,
                                    text="Спасибо за заполнение опросника! Скорее всего, перечисленные вами симптомы являются нормой для вашего срока беременности. Но если у вас остались вопросы, вы можете уточнить их у вашего лечащего врача в чате.", only_patient=True)
    except Exception as e:
        print('connection error', e)


def sender():
    while True:
        try:
            contracts = Contract.query.filter_by(active=True).all()

            for contract in contracts:
                if contract.start:
                    contract.check_orders()
                    contract.check_measurements()

            db.session.commit()
            time.sleep(60 * 5)
        except Exception as e:
            print(e)


@app.route('/message', methods=['POST'])
def save_message():
    data = request.json
    key = data['api_key']

    if key != APP_KEY:
        return "<strong>Некорректный ключ доступа.</strong> Свяжитесь с технической поддержкой."

    return "ok"


@app.route('/frame', methods=['GET'])
def action():
    key = request.args.get('api_key', '')

    if key != APP_KEY:
        return "<strong>Некорректный ключ доступа.</strong> Свяжитесь с технической поддержкой."

    try:
        contract_id = int(request.args.get('contract_id', -1))
        query = Contract.query.filter_by(id=contract_id)

        if query.count() == 0:
            return "<strong>Запрашиваемый канал консультирования не найден.</strong> Попробуйте отключить и заного подключить интеллектуального агента. Если это не сработает, свяжитесь с технической поддержкой."

        return render_template('symptoms.html', contract=query.first())

    except:
        return "error"


def check_params(contract, data):
    report = []
    warnings = []

    if data.get('headache') and check_digit(data.get('headache'), [1, 10]):
        pain = int(data.get('headache'))
        report.append(('headache', pain))

        if pain >= 5:
            warnings.append('головная боль больше 5 баллов')

    if data.get('vomiting') and check_digit(data.get('vomiting'), [1, 10]):
        vomiting = int(data.get('vomiting'))
        report.append(('vomiting', vomiting))

        if vomiting >= 3 or (vomiting > 1 and contract.week() >= 14):
            warnings.append('рвота {} раз(а)'.format(vomiting))

    if data.get('stomachache') == "warning":
        report.append(('stomachache', 1))
        warnings.append('боль в животе')

    if data.get('vision_problems') == "warning":
        report.append(('vision_problems', 1))
        warnings.append('нарушение зрения в виде пелены, тумана и «мелькания мушек»')

    if data.get('itching') == "warning":
        report.append(('itching', 1))
        warnings.append('генерализованный кожный зуд, усиливающийся ночью')

    if data.get('swelling') == "warning":
        report.append(('swelling', 1))
        warnings.append('генерализованные отёки')

    if data.get('liquid_discharge') == "warning":
        report.append(('liquid_discharge', 1))
        warnings.append('жидкие светлые выделения из половых путей')

    if data.get('blood_discharge') == "warning":
        report.append(('blood_discharge', 1))
        warnings.append('кровянистые выделения из половых путей')


    delayed(1, send_warning, [contract.id, warnings])
    delayed(1, agents_api.add_records, [contract.id, report])


@app.route('/frame', methods=['POST'])
def action_save():
    key = request.args.get('api_key', '')
    if key != APP_KEY:
        return "<strong>Некорректный ключ доступа.</strong> Свяжитесь с технической поддержкой."

    try:
        contract_id = int(request.args.get('contract_id', -1))
        query = Contract.query.filter_by(id=contract_id)
        if query.count() == 0:
            return "<strong>Запрашиваемый канал консультирования не найден.</strong> Попробуйте отключить и заного подключить интеллектуального агента. Если это не сработает, свяжитесь с технической поддержкой."
    except:
        return "error"

    contract = query.first()

    check_params(contract, request.form)

    print("{}: Form from {}".format(gts(), contract_id))

    return """
            <strong>Спасибо, окно можно закрыть</strong><script>window.parent.postMessage('close-modal-success','*');</script>
            """

if __name__ == "__main__":
    t = Thread(target=sender)
    t.start()

    app.run(port=PORT, host=HOST)
