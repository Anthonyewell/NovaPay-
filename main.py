import os,uuid,hashlib,secrets
from datetime import datetime,timezone
from dotenv import load_dotenv
from fastapi import FastAPI,HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel,Field
import requests
load_dotenv()
app=FastAPI(title="NovaPay Sandbox v3")
app.add_middleware(CORSMiddleware,allow_origins=["*"],allow_methods=["*"],allow_headers=["*"])
withdrawals=[]; audit=[]
PAYPAL_BASE=os.getenv("PAYPAL_BASE_URL","https://api-m.sandbox.paypal.com")
CLIENT=os.getenv("PAYPAL_CLIENT_ID",""); SECRET=os.getenv("PAYPAL_CLIENT_SECRET","")

def log(action,status,meta=None):
    audit.append({"id":"evt_"+uuid.uuid4().hex[:10],"action":action,"status":status,"created_at":datetime.now(timezone.utc).isoformat(),"meta":meta or {}})

class Withdrawal(BaseModel):
    amount:float=Field(gt=0,le=20000); destination:str; identifier:str; send_to_paypal:bool=False

class VerifyRequest(BaseModel):
    email:str; test_code:str=Field(min_length=6,max_length=6)

@app.get("/api/health")
def health(): return {"ok":True,"environment":"sandbox","real_money":False}

@app.get("/api/verification")
def verification(): return {"email":"TEST_VERIFIED","identity":"TEST_VERIFIED","destination":"TEST_VERIFIED","risk":"SANDBOX","approval":"ENABLED"}

@app.post("/api/verification/email")
def verify_email(v:VerifyRequest):
    if not v.test_code.isdigit(): raise HTTPException(400,"Test code must contain six digits")
    log("Email verification","TEST_VERIFIED",{"email":v.email})
    return {"status":"TEST_VERIFIED","message":"Synthetic verification accepted"}

def paypal_token():
    if not CLIENT or not SECRET: raise HTTPException(503,"PayPal Sandbox credentials are not configured")
    r=requests.post(PAYPAL_BASE+"/v1/oauth2/token",auth=(CLIENT,SECRET),headers={"Accept":"application/json","Accept-Language":"en_US","Content-Type":"application/x-www-form-urlencoded"},data={"grant_type":"client_credentials"},timeout=20)
    if not r.ok: raise HTTPException(502,"PayPal sandbox authentication failed")
    return r.json()["access_token"]

def paypal_payout(amount,email):
    token=paypal_token(); batch="NP-"+uuid.uuid4().hex[:20].upper()
    payload={"sender_batch_header":{"sender_batch_id":batch,"email_subject":"NovaPay Sandbox Test Payout","email_message":"Sandbox test only."},"items":[{"recipient_type":"EMAIL","amount":{"value":f"{amount:.2f}","currency":"USD"},"receiver":email,"note":"NovaPay sandbox test payout","sender_item_id":"NP-"+uuid.uuid4().hex[:10]}]}
    r=requests.post(PAYPAL_BASE+"/v1/payments/payouts",headers={"Authorization":"Bearer "+token,"Content-Type":"application/json","Accept":"application/json","Prefer":"return=representation"},json=payload,timeout=30)
    if not r.ok: raise HTTPException(502,"PayPal sandbox payout failed: "+r.text[:300])
    return r.json().get("batch_header",{}).get("payout_batch_id")

@app.post("/api/withdrawals")
def withdrawal(w:Withdrawal):
    if w.destination not in {"paypal","bitcoin","chime","wells"}: raise HTTPException(400,"Unsupported destination")
    if w.send_to_paypal and w.destination!="paypal": raise HTTPException(400,"PayPal sending requires the PayPal destination")
    item={"id":"wd_"+uuid.uuid4().hex[:12],"amount":w.amount,"destination":w.destination,"identifier":w.identifier,"status":"PENDING_TEST_REVIEW","created_at":datetime.now(timezone.utc).isoformat()}
    if w.send_to_paypal:
        item["paypal_batch_id"]=paypal_payout(w.amount,w.identifier); item["status"]="PAYPAL_SANDBOX_SUBMITTED"; log("PayPal sandbox payout","SUBMITTED",{"id":item["id"]})
    else: log("Withdrawal request","PENDING_TEST_REVIEW",{"id":item["id"],"destination":w.destination})
    withdrawals.append(item); return item

@app.get("/api/audit")
def get_audit():
    return {"items":list(reversed(audit))}

@app.get("/api/withdrawals")
def get_withdrawals(): return {"items":list(reversed(withdrawals))}

@app.get("/api/providers/paypal")
def paypal_status(): return {"provider":"paypal","environment":"sandbox","configured":bool(CLIENT and SECRET),"sandbox_url":"https://www.sandbox.paypal.com/"}


app.mount("/", StaticFiles(directory=".", html=True), name="dashboard")
