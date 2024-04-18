const fs = require('fs');
const ini = require('ini');

const Migrations = artifacts.require('Migrations');
const DataReceiver = artifacts.require('DataMultiReceiver');

module.exports = function(deployer, network, accounts) {
  deployer.then(async() => {
    // deploy migrations
    await deployer.deploy(Migrations);

    // deploy smart contract
    const contract = await deployer.deploy(DataReceiver);

    if(network.startsWith("right")) {

      // update configuration file
      const config = ini.parse(fs.readFileSync('../../configs/local-config-multi.cfg', 'utf-8'));
      const net_config = config[network];

      // update network fields
      base_path = "ledgers/solidity/contracts/";
      net_config.minter = accounts[0];
      net_config.contract = contract.address;
      net_config.contract_abi = base_path + "DataMultiReceiver.abi.json";

      const iniText = ini.stringify(config);
      fs.writeFileSync('../../configs/local-config-multi.cfg', iniText);
    }
  });
}
