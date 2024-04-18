# Interledger Solidity smart contracts

## Installation

You can simply install dependencies with the command below:

```
$ npm install
```

Node.js v5.0+ is recommended for the installation of Truffle. Node.js v12.22.7 (npm v6.14.15) is used during the development.

## Compilation

You can compile the contracts with the following command:

```
$ npx truffle compile
```
It will create the required json files within the build directory.

You might need to remove the previous build directory beforehand:

```
$ rm -r build/
```

## Migration

Then you can run migration files using the below command:

```
$ npx truffle migrate
```

## Testing

Finally you can run tests using truffle internal network using the following command:

```
$ npx truffle test
```

To run a particular test over the smart contract, test file can be specified as the following example:

```
npx truffle test ./test/tokenTest.js
```

Also, you can run tests using external networks (e.g ganache) using the following command:

```
$ npx truffle test --network ganache 
```

Please check the ``` truffle-config.js ``` file for more information about network setting. 