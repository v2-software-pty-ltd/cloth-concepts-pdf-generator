from flask import Flask, request, make_response, render_template
import json
import requests
import logging
import os
import pdfkit
import platform
from dateutil import parser
import urllib.parse

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
app = Flask(__name__)

@app.route('/sales-confirmation-html')
def sales_confirmation_html():
    sales_order_id = request.args.get('sales_order_id')
    if sales_order_id is None:
        sales_order_id = "2999925000000387032"

    argument_json = json.dumps({'sales_order_id': sales_order_id})
    payload = {'arguments': argument_json}

    results = requests.post(
        "https://crm.zoho.com/crm/v2/functions/data_for_sales_confirmation/actions/execute?auth_type=apikey&zapikey=1003.8f64ec64d9560c2c7e810f80fd21e49d.2add21fec0a719b739fa18725edab95b&arguments=" + argument_json,
        data=payload)
    result_dict = json.loads(results.text)

    if ("details" not in result_dict):
        print("Problem with request: " + results.text)

    if ("output" not in result_dict["details"]):
        print("Problem with request: " + results.text)
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

    has_surcharges = any(line_item["Surcharge"] != "" and line_item["Surcharge"] != None and line_item["Surcharge"] > 0 for line_item in sales_order_details["Line_Items"])
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

    shipping_sample_shipment_date = "N/A"
    if shipping_sample_shipment != None and "Ex_mill_date" in shipping_sample_shipment:
        shipping_sample_shipment_date = shipping_sample_shipment["Ex_mill_date"]
    elif "Shipping_Sample_ETA" in sales_order_details:
        shipping_sample_shipment_date = sales_order_details["Shipping_Sample_ETA"]

    sample_shipment_date = "N/A"
    if sample_shipment != None and "Ex_mill_date" in sample_shipment:
        sample_shipment_date = sample_shipment["Ex_mill_date"]
    elif "Sample_ETA" in sales_order_details:
        sample_shipment_date = sales_order_details["Sample_ETA"]

    bulk_shipment_date = "N/A"
    if bulk_shipment != None and "Ex_mill_date" in bulk_shipment:
        bulk_shipment_date = bulk_shipment["Ex_mill_date"]
    elif "Bulk_Delivery_Date" in sales_order_details:
        bulk_shipment_date = sales_order_details["Bulk_Delivery_Date"]

    client_order_number = sales_order_details["Client_Order_Number"] if "Client_Order_Number" in sales_order_details and sales_order_details[
        "Client_Order_Number"] != None else ""

    created_date = parser.parse(sales_order_details["Date"] or sales_order_details["Created_Time"])
    sales_order_details["Date"] = created_date.strftime("%d-%m-%Y")

    if "Yes" in sales_order_details["Tax_Rate_Set_Correctly"]:
        sales_order_details["GST"] = round(sales_order_details["Grand_Total_ex_GST"] * 0.1, 2)
        sales_order_details["Grand_Total_inc_GST"] = round(sales_order_details["Grand_Total_ex_GST"] * 1.1, 2)

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
        "purchase_order_data": output_dict["purchase_order_record"],
        "strike_off": strike_off,
        "lab_dip": lab_dip,
        "client_order_number": client_order_number,
        "has_surcharges": has_surcharges,
        "client": output_dict["client"]
    }


    html = render_template('./sales_confirmation.html', title='Sales Order Confirmation', data=data)
    return html

@app.route('/sales-confirmation')
def sales_confirmation():
    html = sales_confirmation_html()
    options = {
        'page-size': 'A4',
        'dpi': 240,
        'margin-top': '0.15in',
        'margin-right': '0.15in',
        'margin-bottom': '0.15in',
        'margin-left': '0.15in',
        'encoding': "UTF-8",
        'page-width': '20in',
        'no-outline': None
    }

    if (platform.system() == 'Darwin'):
        config = pdfkit.configuration()
    else:
        config = pdfkit.configuration(wkhtmltopdf='./bin/wkhtmltopdf')
    pdf = pdfkit.from_string(html, False, options=options, configuration=config)
    response = make_response(pdf)
    response.headers['Content-Type'] = 'application/pdf'
    sales_order_id = request.args.get('sales_order_id')
    if sales_order_id is None:
        sales_order_id = "2999925000000387032"
    response.headers['Content-Disposition'] = "inline; filename=sales-order-confirmation-" + sales_order_id + ".pdf"
    return response, 200

@app.route('/purchase-order-html')
def purchase_order_html():
    purchase_order_id = request.args.get('purchase_order_id')
    if purchase_order_id is None:
        purchase_order_id = "2999925000000387032"

    argument_json = json.dumps({'purchase_order_id': purchase_order_id})
    payload = {'arguments': argument_json}

    results = requests.post(
        "https://crm.zoho.com/crm/v2/functions/data_for_purchase_order/actions/execute?auth_type=apikey&zapikey=1003.8f64ec64d9560c2c7e810f80fd21e49d.2add21fec0a719b739fa18725edab95b&arguments=" + argument_json,
        data=payload)

    result_dict = json.loads(results.text)

    if ("details" not in result_dict):
        print("Problem with request: " + results.text)

    if ("output" not in result_dict["details"]):
        print("Problem with request: " + results.text)

    output_json = result_dict['details']['output']
    output_dict = json.loads(output_json)
    purchase_order_details = output_dict["purchase_order_data"]
    client_name = purchase_order_details["Client"]["name"] if "Client" in purchase_order_details and purchase_order_details[
        "Client"] != None else ""
    supplier_name = purchase_order_details["Supplier"]["name"] if "Supplier" in purchase_order_details and purchase_order_details[
        "Supplier"] != None else ""
    client_contact_name = purchase_order_details["Client_Contact"]["name"] if "Client_Contact" in purchase_order_details and \
                                                                           purchase_order_details[
                                                                               "Client_Contact"] != None else ""

    created_date = parser.parse(purchase_order_details["Created_Time"])
    purchase_order_details["Date"] = created_date.strftime("%d-%m-%Y")

    product_dict = {}
    for product in output_dict["product_data"]:
        product_dict[product["id"]] = product

    def process_line_item(line_item):
        related_product = product_dict[line_item["Product"]["id"]]
        line_item["Product"] = related_product
        return line_item

    has_surcharges = any(line_item["Supplier_Surcharge"] != "" and line_item["Supplier_Surcharge"] != None and line_item["Supplier_Surcharge"] > 0 for line_item in purchase_order_details["PO_Line_Items"])
    purchase_order_details["PO_Line_Items"] = map(process_line_item, purchase_order_details["PO_Line_Items"])

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

    shipping_sample_shipment_date = "N/A"
    if shipping_sample_shipment != None and "Ex_mill_date" in shipping_sample_shipment:
        shipping_sample_shipment_date = shipping_sample_shipment["Ex_mill_date"]
    elif "Shipping_Sample_Date" in purchase_order_details:
        shipping_sample_shipment_date = purchase_order_details["Shipping_Sample_Date"]

    shipping_sample_notes = ""
    if "Shipping_Sample_Notes" in purchase_order_details:
        shipping_sample_notes = purchase_order_details["Shipping_Sample_Notes"]

    sample_shipment_date = "N/A"
    if sample_shipment != None and "Ex_mill_date" in sample_shipment:
        sample_shipment_date = sample_shipment["Ex_mill_date"]
    elif "Sampling_ETA_Date" in purchase_order_details:
        sample_shipment_date = purchase_order_details["Sampling_ETA_Date"]

    sample_notes = ""
    if "Sampling_Notes" in purchase_order_details:
        sample_notes = purchase_order_details["Sampling_Notes"]

    bulk_shipment_date = "N/A"
    if bulk_shipment != None and "Ex_mill_date" in bulk_shipment:
        bulk_shipment_date = bulk_shipment["Ex_mill_date"]
    elif "Bulk_Delivery_Date" in purchase_order_details:
        bulk_shipment_date = purchase_order_details["Bulk_Delivery_Date"]

    bulk_shipment_notes = ""
    if "Bulk_Delivery_Notes" in purchase_order_details:
        bulk_shipment_notes = purchase_order_details["Bulk_Delivery_Notes"]

    data = {
        "client_contact_name": client_contact_name,
        "client_name": client_name,
        "supplier": output_dict["supplier"],
        "supplier_name": supplier_name,
        "strike_off_lab_dips": strike_off_lab_dips,
        "sample_shipment": sample_shipment,
        "shipping_sample_shipment": shipping_sample_shipment,
        "bulk_shipment": bulk_shipment,
        "shipping_sample_shipment_date": shipping_sample_shipment_date,
        "sample_shipment_date": sample_shipment_date,
        "bulk_shipment_date": bulk_shipment_date,
        "purchase_order_details": purchase_order_details,
        "strike_off": strike_off,
        "lab_dip": lab_dip,
        "has_surcharges": has_surcharges,
        "sample_notes": sample_notes,
        "shipping_sample_notes": shipping_sample_notes,
        "bulk_shipment_notes": bulk_shipment_notes
    }


    html = render_template('./purchase_order.html', title='Purchase Order', data=data)
    return html

@app.route('/purchase-order')
def purchase_order():
    html = purchase_order_html()
    options = {
        'page-size': 'A4',
        'dpi': 240,
        'margin-top': '0.15in',
        'margin-right': '0.15in',
        'margin-bottom': '0.15in',
        'margin-left': '0.15in',
        'encoding': "UTF-8",
        'page-width': '20in',
        'no-outline': None
    }

    if (platform.system() == 'Darwin'):
        config = pdfkit.configuration()
    else:
        config = pdfkit.configuration(wkhtmltopdf='./bin/wkhtmltopdf')
    pdf = pdfkit.from_string(html, False, options=options, configuration=config)
    response = make_response(pdf)
    response.headers['Content-Type'] = 'application/pdf'
    purchase_order_id = request.args.get('purchase_order_id')
    response.headers['Content-Disposition'] = "inline; filename=purchase-order-" + purchase_order_id + ".pdf"
    return response, 200

# PO pro-forma
@app.route('/pro-forma-purchase-order-html')
def pro_forma_purchase_order_html():
    purchase_order_id = request.args.get('purchase_order_id')
    if purchase_order_id is None:
        purchase_order_id = "2999925000000387032"

    argument_json = json.dumps({'purchase_order_id': purchase_order_id})
    payload = {'arguments': argument_json}

    results = requests.post(
        "https://crm.zoho.com/crm/v2/functions/data_for_purchase_order/actions/execute?auth_type=apikey&zapikey=1003.8f64ec64d9560c2c7e810f80fd21e49d.2add21fec0a719b739fa18725edab95b&arguments=" + argument_json,
        data=payload)

    result_dict = json.loads(results.text)

    if ("details" not in result_dict):
        print("Problem with request: " + results.text)

    if ("output" not in result_dict["details"]):
        print("Problem with request: " + results.text)

    output_json = result_dict['details']['output']
    output_dict = json.loads(output_json)
    purchase_order_details = output_dict["purchase_order_data"]
    supplier_name = purchase_order_details["Supplier"]["name"] if "Supplier" in purchase_order_details and purchase_order_details[
        "Supplier"] != None else ""

    data = {
        "supplier_name": supplier_name
    }

    html = render_template('./Pro_Forma_Purchase_Order.html',
                           title='Purchase Order', data=data)
    return html


@app.route('/pro-forma-purchase-order')
def pro_forma_purchase_order():
    html = purchase_order_html()
    options = {
        'page-size': 'A4',
        'dpi': 240,
        'margin-top': '0.15in',
        'margin-right': '0.15in',
        'margin-bottom': '0.15in',
        'margin-left': '0.15in',
        'encoding': "UTF-8",
        'page-width': '20in',
        'no-outline': None
    }

    if (platform.system() == 'Darwin'):
        config = pdfkit.configuration()
    else:
        config = pdfkit.configuration(wkhtmltopdf='./bin/wkhtmltopdf')
    pdf = pdfkit.from_string(
        html, False, options=options, configuration=config)
    response = make_response(pdf)
    response.headers['Content-Type'] = 'application/pdf'
    purchase_order_id = request.args.get('purchase_order_id')
    response.headers['Content-Disposition'] = "inline; filename=purchase-order-" + \
        purchase_order_id + ".pdf"
    return response, 200

@app.route('/strike-off-lab-dip-html')
def strike_off_lab_dip_html():
    strike_off_lab_dip_id = request.args.get('strike_off_lab_dip_id')
    if strike_off_lab_dip_id is None:
        strike_off_lab_dip_id = "2999925000000387032"

    argument_json = json.dumps({'record_id': strike_off_lab_dip_id})
    payload = {'arguments': argument_json}

    results = requests.post(
        "https://crm.zoho.com/crm/v2/functions/data_for_strike_off_lab_dip/actions/execute?auth_type=apikey&zapikey=1003.8f64ec64d9560c2c7e810f80fd21e49d.2add21fec0a719b739fa18725edab95b&arguments=" + argument_json,
        data=payload)
    result_dict = json.loads(results.text)

    if ("details" not in result_dict):
        print("Problem with request: " + results.text)

    if ("output" not in result_dict["details"]):
        print("Problem with request: " + results.text)
    output_json = result_dict['details']['output']
    output_dict = json.loads(output_json)

    strike_off_lab_dip = output_dict["strike_off_lab_dip"]

    sent_date = parser.parse(strike_off_lab_dip["Date_Sent"] or strike_off_lab_dip["Created_Time"])
    strike_off_lab_dip["Date_Sent"] = sent_date.strftime("%d/%m/%Y")

    ex_mill_date = parser.parse(strike_off_lab_dip["Due_Date"] or strike_off_lab_dip["Created_Time"])
    strike_off_lab_dip["Due_Date"] = ex_mill_date.strftime("%d/%m/%Y")

    data = {
        "strike_off_lab_dip": strike_off_lab_dip,
        "supplier": output_dict["supplier"]
    }

    if strike_off_lab_dip["Strike_Off_or_Lab_Dip"] == "Strike-Off":
        html = render_template('./strike_off.html', title='Strike Off', data=data)
    elif strike_off_lab_dip["Strike_Off_or_Lab_Dip"] == "Lab-Dip":
        html = render_template('./lab_dip.html', title='Strike Off', data=data)
    return html

@app.route('/strike-off-lab-dip')
def strike_off_lab_dip():
    html = strike_off_lab_dip_html()
    options = {
        'page-size': 'A4',
        'dpi': 240,
        'margin-top': '0.15in',
        'margin-right': '0.15in',
        'margin-bottom': '0.15in',
        'margin-left': '0.15in',
        'encoding': "UTF-8",
        'page-width': '20in',
        'no-outline': None
    }

    if (platform.system() == 'Darwin'):
        config = pdfkit.configuration()
    else:
        config = pdfkit.configuration(wkhtmltopdf='./bin/wkhtmltopdf')
    pdf = pdfkit.from_string(html, False, options=options, configuration=config)
    response = make_response(pdf)
    response.headers['Content-Type'] = 'application/pdf'
    strike_off_lab_dip_id = request.args.get('strike_off_lab_dip_id')
    if strike_off_lab_dip_id is None:
        strike_off_lab_dip_id = "2999925000000387032"
    response.headers['Content-Disposition'] = "inline; filename=strike-off-lab-dip-" + strike_off_lab_dip_id + ".pdf"
    return response, 200

@app.route('/sampling-order-html')
def sampling_order_html():
    sampling_order_id = request.args.get('sampling_order_id')

    argument_json = json.dumps({'record_id': sampling_order_id})
    payload = {'arguments': argument_json}

    results = requests.post(
        "https://crm.zoho.com/crm/v2/functions/data_for_sampling_order/actions/execute?auth_type=apikey&zapikey=1003.8f64ec64d9560c2c7e810f80fd21e49d.2add21fec0a719b739fa18725edab95b&arguments=" + argument_json,
        data=payload)
    result_dict = json.loads(results.text)

    if ("details" not in result_dict):
        print("Problem with request: " + results.text)

    if ("output" not in result_dict["details"]):
        print("Problem with request: " + results.text)
    output_json = result_dict['details']['output']
    output_dict = json.loads(output_json)

    sampling_order = output_dict["sampling_order"]

    order_date = parser.parse(sampling_order["Date_Ordered"] or sampling_order["Created_Time"])
    sampling_order["Date_Ordered"] = order_date.strftime("%d/%m/%Y")

    received_date = parser.parse(sampling_order["Date_Received"] or sampling_order["Created_Time"])
    sampling_order["Date_Received"] = received_date.strftime("%d/%m/%Y")

    data = {
        "sampling_order": sampling_order,
        "supplier": output_dict["supplier"]
    }
    return render_template('./Sampling_Order_Form.html', title='Sampling Order', data=data)

@app.route('/sampling-order')
def sampling_order():
    html = sampling_order_html()
    options = {
        'page-size': 'A4',
        'dpi': 240,
        'margin-top': '0.15in',
        'margin-right': '0.15in',
        'margin-bottom': '0.15in',
        'margin-left': '0.15in',
        'encoding': "UTF-8",
        'page-width': '20in',
        'no-outline': None
    }

    if (platform.system() == 'Darwin'):
        config = pdfkit.configuration()
    else:
        config = pdfkit.configuration(wkhtmltopdf='./bin/wkhtmltopdf')
    pdf = pdfkit.from_string(html, False, options=options, configuration=config)
    response = make_response(pdf)
    response.headers['Content-Type'] = 'application/pdf'
    sampling_order_id = request.args.get('sampling_order_id')
    if sampling_order_id is None:
        sampling_order_id = "2999925000000387032"
    response.headers['Content-Disposition'] = "inline; filename=sampling-order-" + sampling_order_id + ".pdf"
    return response, 200

@app.route('/agency-commission-html')
def agency_commission_html():
    supplier_id = request.args.get('supplier_id')
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')

    argument_json = json.dumps({'supplier_id': supplier_id, 'start_date_str': start_date, 'end_date_str': end_date})
    payload = {'arguments': argument_json}

    results = requests.post(
        "https://crm.zoho.com/crm/v2/functions/data_for_agency_commission_report/actions/execute?auth_type=apikey&zapikey=1003.8f64ec64d9560c2c7e810f80fd21e49d.2add21fec0a719b739fa18725edab95b&arguments=" + argument_json,
        data=payload)

    print("https://crm.zoho.com/crm/v2/functions/data_for_agency_commission_report/actions/execute?auth_type=apikey&zapikey=1003.8f64ec64d9560c2c7e810f80fd21e49d.2add21fec0a719b739fa18725edab95b&arguments=" + argument_json)
    result_dict = json.loads(results.text)

    if ("details" not in result_dict):
        print("Problem with request: " + results.text)

    if ("output" not in result_dict["details"]):
        print("Problem with request: " + results.text)
    output_json = result_dict['details']['output']
    output_dict = json.loads(output_json)

    purchase_orders_for_supplier = output_dict["purchase_orders_for_supplier"]
    totals_data_per_currency = dict()
    for purchase_order in purchase_orders_for_supplier:
      currency = purchase_order["Currency"]
      print("currency" + currency)
      commission = purchase_order["Commission_Due"]
      total_data_for_this_currency = totals_data_per_currency[currency] if currency in totals_data_per_currency else dict()
      current_commission_total = total_data_for_this_currency['commission'] if 'commission' in total_data_for_this_currency else 0
      total_data_for_this_currency['commission'] = current_commission_total + commission

      grand_total = purchase_order["Grand_Total_inc_GST"]
      current_order_total = total_data_for_this_currency['order_total'] if 'order_total' in total_data_for_this_currency else 0
      total_data_for_this_currency['order_total'] = current_order_total + grand_total
      totals_data_per_currency[currency] = total_data_for_this_currency

    print(totals_data_per_currency)
    data = {
        "purchase_orders_for_supplier": purchase_orders_for_supplier,
        "totals_data_per_currency": totals_data_per_currency,
        "supplier": output_dict["supplier"]
    }
    return render_template('./Agency_Commission.html', title='Sampling Order', data=data)

@app.route('/agency-commission')
def agency_commission():
    html = agency_commission_html()
    options = {
        'page-size': 'A4',
        'dpi': 240,
        'margin-top': '0.15in',
        'margin-right': '0.15in',
        'margin-bottom': '0.15in',
        'margin-left': '0.15in',
        'encoding': "UTF-8",
        'page-width': '20in',
        'no-outline': None
    }

    if (platform.system() == 'Darwin'):
        config = pdfkit.configuration()
    else:
        config = pdfkit.configuration(wkhtmltopdf='./bin/wkhtmltopdf')
    pdf = pdfkit.from_string(html, False, options=options, configuration=config)
    response = make_response(pdf)
    response.headers['Content-Type'] = 'application/pdf'
    supplier_id = request.args.get('supplier_id')
    if supplier_id is None:
        supplier_id = "2999925000000387032"
    response.headers['Content-Disposition'] = "inline; filename=agency-commission-" + supplier_id + ".pdf"
    return response, 200

port = int(os.getenv('PORT', 8084))
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=port)
