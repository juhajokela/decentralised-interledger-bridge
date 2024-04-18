const fs = require('fs');
const ini = require('ini');

const Migrations = artifacts.require('Migrations');
const DataSender = artifacts.require('DataSender');

module.exports = function(deployer, network, accounts) {
  deployer.then(async() => {
    // deploy migrations
    await deployer.deploy(Migrations);

    // deploy smart contract
    const contract = await deployer.deploy(DataSender);

    if(network == "left" || network == "right" ||
        network == "compose_left" || network == "compose_right") {
      // update configuration file
      const config = ini.parse(fs.readFileSync('../local-config.cfg', 'utf-8'));
      const net_config = config[network];

      // update network fields
      base_path = "ledgers/solidity/contracts/";
      net_config.minter = accounts[0];
      net_config.contract = contract.address;
      net_config.contract_abi = base_path + "DataSender.abi.json";

      const iniText = ini.stringify(config);
      fs.writeFileSync('../../local-config.cfg', iniText);
    }
  });
}
