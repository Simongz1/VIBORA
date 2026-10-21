// The C++ server owns the GUI/API; agent jobs and HPC work remain asynchronous.
void workflow_proxy(const std::string& path,const std::string& body,httplib::Response& r) {
 try {
  const char* port=std::getenv("VIBORA_AGENT_PORT");
  if(!port)throw std::runtime_error("Agent bridge is offline. Start scripts/agent_bridge.py.");
  httplib::Client client("127.0.0.1",std::stoi(port));
  client.set_connection_timeout(3);client.set_read_timeout(45);client.set_write_timeout(10);
  httplib::Headers headers;
  if(const char* token=std::getenv("VIBORA_AGENT_TOKEN"))headers.emplace("Authorization",std::string("Bearer ")+token);
  auto result=client.Post(path,headers,body,"application/json");
  if(!result)throw std::runtime_error("Agent bridge is unreachable or did not answer within 45 s. Check the bridge terminal on your laptop and restart it if it stopped.");
  r.status=result->status;
  if(json::accept(result->body))r.set_content(result->body,"application/json");
  else r.set_content(json({{"error","Agent bridge returned HTTP "+std::to_string(result->status)+": "+result->body.substr(0,300)}}).dump(),"application/json");
 }catch(const std::exception& e){r.status=503;r.set_content(json({{"error",e.what()}}).dump(),"application/json");}
}
void register_workflow(httplib::Server& server) {
 server.Get("/api/models",[](const auto&,auto& r){workflow_proxy("/models","{}",r);});
 for(const std::string action:{"start","status","approve","reject","run","cancel_run"}) {
  server.Post("/api/jobs/"+action,[action](const auto& req,auto& r){
   if(req.get_header_value("Content-Type")!="application/json"){r.status=415;return;}
   workflow_proxy("/jobs/"+action,req.body,r);
  });
 }
 server.Post("/api/graph/check",[](const auto& req,auto& r){workflow_proxy("/graph/check",req.body,r);});
}
