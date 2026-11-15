//+------------------------------------------------------------------+
//| KafkaSignalPaperContract.mqh                                     |
//| RESEARCH-ONLY SignalRecord JSON contract.                        |
//|                                                                  |
//| Publish signals as JSON. Never place orders from Kafka.          |
//| Never open sockets or speak the article's binary protocol.       |
//| This include is a JSON contract, not production transport.       |
//|                                                                  |
//| Do NOT copy this file with scripts/18-install-forex-indicator.sh |
//| Do NOT attach anything that includes this to funded prefixes.    |
//| File bridge (Mt5ArchBridge) remains desk / position truth.       |
//+------------------------------------------------------------------+
#property copyright "mt5-arch-integration"
#property strict

#ifndef KAFKA_SIGNAL_PAPER_CONTRACT_MQH
#define KAFKA_SIGNAL_PAPER_CONTRACT_MQH

#define KAFKA_SIGNAL_SCHEMA_VERSION  1
#define KAFKA_SIGNAL_FIELD_COUNT     8
#define KAFKA_SIGNAL_PAPER_TOPIC     "mt5.signals.paper.v1"

//+------------------------------------------------------------------+
//| Paper-only payload. book_mode must stay "paper" in this stub.    |
//+------------------------------------------------------------------+
struct KafkaPaperSignalRecord
  {
   int               schema_version;
   string            symbol;
   string            side;          // "buy" | "sell" | "flat"
   string            timeframe;
   string            strategy_id;
   string            terminal_id;
   string            ts;            // UTC, e.g. 2026-06-15T12:00:00Z
   string            book_mode;     // "paper" only in this stub
   string            signal_type;   // optional article alias
   double            entry;
   double            sl;
   double            tp;
   double            confidence;
   string            partition_key;
  };

//+------------------------------------------------------------------+
bool KafkaPaperSignalContractCheck()
  {
   int actual_fields = 8;  // required JSON fields; keep in sync with schema
   if(actual_fields != KAFKA_SIGNAL_FIELD_COUNT)
     {
      PrintFormat("FATAL paper-signal contract: serializer fields %d != %d",
                  actual_fields, KAFKA_SIGNAL_FIELD_COUNT);
      return false;
     }
   if(KAFKA_SIGNAL_SCHEMA_VERSION != 1)
     {
      Print("FATAL paper-signal contract: unsupported schema_version");
      return false;
     }
   return true;
  }

//+------------------------------------------------------------------+
string KafkaPaperSignalPartitionKey(const KafkaPaperSignalRecord &sig)
  {
   if(StringLen(sig.partition_key) > 0)
      return sig.partition_key;
   return sig.symbol + "_" + sig.timeframe;
  }

//+------------------------------------------------------------------+
//| JSON for a paper record. Empty string = refuse to emit.          |
//| No orders. No sockets.                                           |
//+------------------------------------------------------------------+
string KafkaPaperSignalToJson(const KafkaPaperSignalRecord &sig)
  {
   if(sig.schema_version != KAFKA_SIGNAL_SCHEMA_VERSION)
     {
      PrintFormat("FATAL paper-signal: record v%d, stub built for v%d",
                  sig.schema_version, KAFKA_SIGNAL_SCHEMA_VERSION);
      return "";
     }
   if(sig.book_mode != "paper")
     {
      Print("REFUSE paper-signal: book_mode is not paper");
      return "";
     }
   if(!KafkaPaperSignalContractCheck())
      return "";
   string key = KafkaPaperSignalPartitionKey(sig);
   return StringFormat(
      "{\"schema_version\":%d,\"symbol\":\"%s\",\"side\":\"%s\","
      "\"timeframe\":\"%s\",\"strategy_id\":\"%s\",\"terminal_id\":\"%s\","
      "\"ts\":\"%s\",\"book_mode\":\"paper\",\"signal_type\":\"%s\","
      "\"entry\":%.5f,\"sl\":%.5f,\"tp\":%.5f,\"confidence\":%.4f,"
      "\"partition_key\":\"%s\"}",
      sig.schema_version,
      sig.symbol,
      sig.side,
      sig.timeframe,
      sig.strategy_id,
      sig.terminal_id,
      sig.ts,
      sig.signal_type,
      sig.entry,
      sig.sl,
      sig.tp,
      sig.confidence,
      key);
  }

#endif
