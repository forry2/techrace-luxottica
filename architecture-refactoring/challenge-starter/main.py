import os

from dotenv import load_dotenv
from flask import Flask, jsonify, request

from app import db, orders, shipping, warehouse
from app.orders import StockError
from app.validators import validate_order_payload

load_dotenv()


def create_app():
    db.init_db()
    warehouse.initialize_stock_cache()

    flask_app = Flask(__name__, template_folder="app/templates")

    @flask_app.get("/warehouses")
    def get_warehouses():
        return jsonify(warehouse.list_warehouses())

    @flask_app.get("/stock/<sku>")
    def get_stock(sku):
        return jsonify({"sku": sku, "quantity": warehouse.get_stock(sku)})

    @flask_app.post("/stock/<sku>/restock")
    def restock(sku):
        payload = request.get_json(silent=True) or {}
        quantity = payload.get("quantity", 0)
        warehouse.restock(sku, quantity)
        return jsonify({"sku": sku, "quantity": warehouse.get_stock(sku)}), 200

    @flask_app.get("/orders")
    def get_orders():
        return jsonify(orders.list_orders())

    @flask_app.post("/orders")
    def post_order():
        payload = request.get_json(silent=True) or {}
        error = validate_order_payload(payload)
        if error:
            return jsonify({"error": error}), 400
        order = orders.create_order(payload["customer_name"], payload["lines"])
        return jsonify(order), 201

    @flask_app.get("/orders/<int:order_id>")
    def get_order(order_id):
        order = orders.get_order(order_id)
        if order is None:
            return jsonify({"error": "not found"}), 404
        return jsonify(order)

    @flask_app.post("/orders/<int:order_id>/confirm")
    def confirm_order(order_id):
        try:
            order = orders.confirm_order(order_id)
        except StockError as e:
            return jsonify({"error": str(e)}), 400
        if order is None:
            return jsonify({"error": "not found"}), 404
        return jsonify(order), 200

    @flask_app.post("/orders/<int:order_id>/cancel")
    def cancel_order(order_id):
        try:
            order = orders.cancel_order(order_id)
        except StockError as e:
            return jsonify({"error": str(e)}), 400
        if order is None:
            return jsonify({"error": "not found"}), 404
        return jsonify(order), 200

    @flask_app.get("/shipments")
    def get_shipments():
        return jsonify(shipping.list_shipments())

    # Registra il blueprint del chatbot/assistente AI solo se le credenziali sono presenti.
    # Senza WATSONX_API_KEY l'app si avvia comunque e tutti gli endpoint core restano attivi.
    if os.environ.get("WATSONX_API_KEY"):
        from app.assistant import bp as assistant_bp  # noqa: PLC0415
        flask_app.register_blueprint(assistant_bp)
    else:
        print("[wareflow] WATSONX_API_KEY non impostata — blueprint assistant non registrato")

    return flask_app


app = create_app()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080, threaded=True)
