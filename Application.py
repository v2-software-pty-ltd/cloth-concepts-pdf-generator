from flask import Flask, request
from flask import render_template
from flask_weasyprint import HTML, render_pdf
import json
import requests

app = Flask(__name__)


@app.route('/hello-world')
def hello_world():
    return 'Hello World'


@app.route('/sales-confirmation')
def sales_confirmation():
    sales_order_id = request.args.get('sales_order_id')
    if sales_order_id is None:
        sales_order_id = "2999925000000387032"

    argument_json = json.dumps({'sales_order_id': sales_order_id})
    payload = {'arguments': argument_json}

    results = requests.post(
        "https://crm.zoho.com/crm/v2/functions/data_for_sales_confirmation/actions/execute?auth_type=apikey&zapikey=1003.8f64ec64d9560c2c7e810f80fd21e49d.2add21fec0a719b739fa18725edab95b",
        data=payload)
    result_dict = json.loads(results.text)
    output_json = result_dict['details']['output']
    output_dict = json.loads(output_json)
    sales_order_details = output_dict["sales_order_data"]
    client_name = sales_order_details["Client"]["name"] if "Client" in sales_order_details and sales_order_details[
        "Client"] != None else ""
    client_contact_name = sales_order_details["Client_Contact"]["name"] if "Client_Contact" in sales_order_details and \
                                                                           sales_order_details[
                                                                               "Client_Contact"] != None else ""

    product_dict = {}
    for product in output_dict["product_data"]:
        product_dict[product["id"]] = product

    def process_line_item(line_item):
        related_product = product_dict[line_item["Product"]["id"]]
        line_item["Product"] = related_product
        return line_item

    sales_order_details["Line_Items"] = map(process_line_item, sales_order_details["Line_Items"])

    strike_off_lab_dips = output_dict["strike_off_lab_dips"]
    strike_off = None
    lab_dip = None
    for strike_off_lab_dip in strike_off_lab_dips:
        if strike_off_lab_dip["Strike_Off_or_Lab_Dip"] == "Strike-Off":
            strike_off = strike_off_lab_dip
        else:
            lab_dip = strike_off_lab_dip
    shipments = output_dict["shipments"]
    sample_shipment = None
    shipping_sample_shipment = None
    bulk_shipment = None
    for shipment in shipments:
        shipment_type = shipment["Shipment_Type"] if "Shipment_Type" in shipment else ""
        if (shipment_type == "Bulk Shipment"):
            bulk_shipment = shipment
        elif (shipment_type == "Sample"):
            sample_shipment = shipment
        elif (shipment_type == "Shipping Sample"):
            shipping_sample_shipment = shipment

    shipping_sample_shipment_date = shipping_sample_shipment[
        "Ex_mill_date"] if shipping_sample_shipment != None and "Ex_mill_date" in shipping_sample_shipment else "N/A"
    sample_shipment_date = sample_shipment[
        "Ex_mill_date"] if sample_shipment != None and "Ex_mill_date" in sample_shipment else "N/A"
    bulk_shipment_date = bulk_shipment[
        "Ex_mill_date"] if bulk_shipment != None and "Ex_mill_date" in bulk_shipment else "N/A"

    data = {
        "client_contact_name": client_contact_name,
        "client_name": client_name,
        "strike_off_lab_dips": strike_off_lab_dips,
        "sample_shipment": sample_shipment,
        "shipping_sample_shipment": shipping_sample_shipment,
        "bulk_shipment": bulk_shipment,
        "shipping_sample_shipment_date": shipping_sample_shipment_date,
        "sample_shipment_date": sample_shipment_date,
        "bulk_shipment_date": bulk_shipment_date,
        "sales_order_details": sales_order_details,
        "strike_off": strike_off,
        "lab_dip": lab_dip
    }

    html = render_template('./sales_confirmation.html', title='Sales Order Confirmation', data=data)
    return render_pdf(HTML(string=html))
